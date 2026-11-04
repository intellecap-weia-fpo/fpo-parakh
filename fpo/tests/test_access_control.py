import sys
import types
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from graphql_jwt.shortcuts import get_token

from fpo import report_access
from fpo.models import FPO, FPOMember, YearlySubmission

User = get_user_model()
PASSWORD = "Fpo-Access-Strong-762!"


class FakeHTML:
    def __init__(self, *args, **kwargs):
        pass

    def write_pdf(self, *args, **kwargs):
        return b"%PDF-1.4 test"


# WeasyPrint needs native libraries that CI and dev machines may lack; the view only needs HTML/CSS.
FAKE_WEASYPRINT = types.SimpleNamespace(HTML=FakeHTML, CSS=lambda *args, **kwargs: None)


class AccessControlTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user("member@example.com", "member@example.com", PASSWORD)
        self.outsider = User.objects.create_user("outsider@example.com", "outsider@example.com", PASSWORD)
        self.admin = User.objects.create_user("admin@example.com", "admin@example.com", PASSWORD)
        self.admin.groups.add(Group.objects.get_or_create(name="admin")[0])
        self.fpo = FPO.objects.create(
            name="Test FPO",
            email="org@example.com",
            phone="9876543210",
            address_line_1="Farm Road",
            city="Pune",
            district="Pune",
            state="Maharashtra",
            pincode="411001",
            created_by=self.member,
        )
        FPOMember.objects.create(fpo=self.fpo, user=self.member, role="member")
        self.submission = YearlySubmission(fpo=self.fpo, financial_year="2025-26", submitted_by=self.member)
        self.submission.save(skip_score_calculation=True)
        self.pdf_url = reverse("fpo:submission_pdf_report", args=[self.fpo.pk, self.submission.pk])
        self.link_url = reverse("fpo:submission_pdf_link", args=[self.fpo.pk, self.submission.pk])

    def get_pdf(self, url):
        with patch("fpo.views._build_submission_report_context", return_value={}), patch.dict(
            sys.modules, {"weasyprint": FAKE_WEASYPRINT}
        ):
            return self.client.get(url)

    def test_pdf_report_requires_login(self):
        response = self.get_pdf(self.pdf_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response["Location"])

    def test_pdf_report_refuses_users_outside_the_fpo(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.get_pdf(self.pdf_url).status_code, 403)

    def test_pdf_report_allows_fpo_members(self):
        self.client.force_login(self.member)
        response = self.get_pdf(self.pdf_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_pdf_link_needs_a_token_with_access(self):
        self.assertEqual(self.client.get(self.link_url).status_code, 401)
        bad = self.client.get(self.link_url, HTTP_AUTHORIZATION="Bearer " + get_token(self.outsider))
        self.assertEqual(bad.status_code, 403)

    def test_signed_link_opens_without_session_and_only_for_its_submission(self):
        response = self.client.get(self.link_url, HTTP_AUTHORIZATION="Bearer " + get_token(self.member))
        self.assertEqual(response.status_code, 200)
        url = response.json()["url"]
        self.assertEqual(self.get_pdf(url).status_code, 200)
        other_sig = report_access.sign_pdf_link(self.fpo.pk, self.submission.pk + 1)
        self.assertEqual(self.get_pdf(f"{self.pdf_url}?sig={other_sig}").status_code, 403)
        self.assertEqual(self.get_pdf(f"{self.pdf_url}?sig=forged").status_code, 403)

    def test_only_admins_can_manage_users(self):
        self.client.force_login(self.member)
        delete_url = reverse("fpo:delete_user", args=[self.outsider.pk])
        self.assertEqual(self.client.post(delete_url).status_code, 403)
        self.assertEqual(self.client.get(reverse("fpo:user_management")).status_code, 403)
        self.assertEqual(self.client.post(reverse("fpo:create_user"), {}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.outsider.pk).exists())

    def test_delete_user_rejects_get_and_works_for_admin_post(self):
        self.client.force_login(self.admin)
        delete_url = reverse("fpo:delete_user", args=[self.outsider.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 405)
        self.client.post(delete_url)
        self.assertFalse(User.objects.filter(pk=self.outsider.pk).exists())

    def test_document_upload_page_requires_login(self):
        response = self.client.get(reverse("fpo:fpo_document_upload", args=[self.fpo.pk]))
        self.assertEqual(response.status_code, 302)

    def test_document_processing_api_requires_login(self):
        response = self.client.post(reverse("fpo:process_fpo_document"), {"fpo_id": self.fpo.pk})
        self.assertEqual(response.status_code, 401)

    def test_outsiders_cannot_read_fpo_pages_or_exports(self):
        self.client.force_login(self.outsider)
        urls = [
            reverse("fpo:fpo_detail", args=[self.fpo.pk]),
            reverse("fpo:submission_detail", args=[self.fpo.pk, self.submission.pk]),
            reverse("fpo:submission_report_view", args=[self.fpo.pk, self.submission.pk]),
            reverse("fpo:export_fpo_details", args=[self.fpo.pk]),
            reverse("fpo:export_yearly_submissions"),
            reverse("fpo:search_users") + "?q=example",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_outsiders_cannot_make_themselves_fpo_admin(self):
        self.client.force_login(self.outsider)
        response = self.client.post(
            reverse("fpo:add_member", args=[self.fpo.pk]), {"user_id": self.outsider.pk, "role": "admin"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FPOMember.objects.filter(fpo=self.fpo, user=self.outsider).exists())
        member = FPOMember.objects.get(fpo=self.fpo, user=self.member)
        self.assertEqual(self.client.post(reverse("fpo:remove_member", args=[self.fpo.pk, member.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("fpo:recalculate_scores", args=[self.fpo.pk])).status_code, 403)

    def test_fpo_admin_can_add_members_but_only_with_known_roles(self):
        FPOMember.objects.filter(fpo=self.fpo, user=self.member).update(role="admin")
        self.client.force_login(self.member)
        url = reverse("fpo:add_member", args=[self.fpo.pk])
        self.client.post(url, {"user_id": self.outsider.pk, "role": "owner"})
        self.assertFalse(FPOMember.objects.filter(fpo=self.fpo, user=self.outsider).exists())
        self.client.post(url, {"user_id": self.outsider.pk, "role": "viewer"})
        self.assertTrue(FPOMember.objects.filter(fpo=self.fpo, user=self.outsider, role="viewer").exists())

    def test_store_link_must_be_http(self):
        FPOMember.objects.filter(fpo=self.fpo, user=self.member).update(role="admin")
        self.client.force_login(self.member)
        url = reverse("fpo:update_store_link", args=[self.fpo.pk])
        self.client.post(url, {"store_link": "javascript:alert(1)"})
        self.fpo.refresh_from_db()
        self.assertIsNone(self.fpo.store_link)
        self.client.post(url, {"store_link": "https://example.com/shop"})
        self.fpo.refresh_from_db()
        self.assertEqual(self.fpo.store_link, "https://example.com/shop")

    def test_staff_cannot_delete_a_superuser(self):
        staff = User.objects.create_user("staff@example.com", "staff@example.com", PASSWORD, is_staff=True)
        root = User.objects.create_superuser("root@example.com", "root@example.com", PASSWORD)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(reverse("fpo:delete_user", args=[root.pk])).status_code, 403)
        self.assertTrue(User.objects.filter(pk=root.pk).exists())

    def test_manage_pages_are_superuser_only(self):
        self.client.force_login(self.outsider)
        edit = reverse("management:user_edit", args=[self.outsider.pk])
        self.client.post(edit, {"username": "outsider@example.com", "email": "outsider@example.com", "is_active": "on", "role": "admin"})
        self.outsider.refresh_from_db()
        self.assertFalse(self.outsider.is_superuser)
        for url in (reverse("management:user_list"), reverse("management:user_create"), reverse("management:dashboard")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        detail = reverse("management:user_detail", args=[self.member.pk])
        self.assertEqual(self.client.post(detail, {"action": "delete"}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())

    def test_graphql_hides_user_accounts_and_drafts(self):
        from fpo.models import FPOVerificationStatus

        FPO.objects.filter(pk=self.fpo.pk).update(verification_status=FPOVerificationStatus.APPROVED, is_active=True)
        leak = self.client.post(
            "/graphql/",
            {"query": "{ allFpos { edges { node { createdBy { email } } } } }"},
            content_type="application/json",
        )
        self.assertIn("createdBy", leak.content.decode())  # error mentions the unknown field
        self.assertNotIn("member@example.com", leak.content.decode())
        drafts = self.client.post(
            "/graphql/",
            {"query": "{ allFpos { edges { node { yearlySubmissions { edges { node { status } } } } } } }"},
            content_type="application/json",
        ).json()
        statuses = [
            s["node"]["status"]
            for f in drafts["data"]["allFpos"]["edges"]
            for s in f["node"]["yearlySubmissions"]["edges"]
        ]
        self.assertNotIn("DRAFT", statuses)

    def test_upload_page_is_for_fpo_admins(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("fpo:fpo_document_upload", args=[self.fpo.pk])).status_code, 403)

    def test_graphql_user_lookup_and_reviewer_are_private(self):
        import base64

        staff = User.objects.create_user("staffer@example.com", "staffer@example.com", PASSWORD, is_staff=True)
        node_id = base64.b64encode(f"UserNode:{staff.pk}".encode()).decode()
        body = self.client.post(
            "/graphql/",
            {"query": '{ user(id: "%s") { email } }' % node_id},
            content_type="application/json",
        ).content.decode()
        self.assertNotIn("staffer@example.com", body)
        body = self.client.post(
            "/graphql/",
            {"query": "{ allFpos { edges { node { reviewedBy { email } } } } }"},
            content_type="application/json",
        ).content.decode()
        self.assertNotIn("@example.com", body)

    def test_fpo_admins_can_only_find_users_by_exact_email(self):
        FPOMember.objects.filter(fpo=self.fpo, user=self.member).update(role="admin")
        self.client.force_login(self.member)
        url = reverse("fpo:search_users")
        self.assertEqual(self.client.get(url + "?q=example").json()["users"], [])
        found = self.client.get(url + "?q=outsider@example.com").json()["users"]
        self.assertEqual([u["id"] for u in found], [self.outsider.pk])
        self.assertNotIn("email", found[0])
