from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import logging
import uuid
from django.utils import timezone
from datetime import timedelta


logger = logging.getLogger(__name__)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    profile_image = models.ImageField(upload_to="profile_images/", null=True, blank=True)
    cover_image = models.ImageField(upload_to="cover_images/", null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    preferred_language = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        help_text="User's preferred language for the interface"
    )
    # Email verification fields
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(default=uuid.uuid4, editable=False)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def get_absolute_url(self):
        return reverse("management:user_detail", kwargs={"user_id": self.user.id})

    @property
    def has_profile_image(self):
        return bool(self.profile_image)

    @property
    def has_cover_image(self):
        return bool(self.cover_image)
    
    def generate_verification_token(self):
        """Generate new verification token"""
        self.email_verification_token = uuid.uuid4()
        self.email_verification_sent_at = timezone.now()
        self.save()
        return self.email_verification_token
    
    def is_verification_token_expired(self):
        """Check if verification token is expired (24 hours)"""
        if not self.email_verification_sent_at:
            return True
        expiry_time = self.email_verification_sent_at + timedelta(hours=24)
        return timezone.now() > expiry_time
    
    def verify_email(self):
        """Mark email as verified"""
        self.email_verified = True
        self.email_verification_token = uuid.uuid4()  # Invalidate token
        self.save()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def send_user_verification_email(sender, instance, created, **kwargs):
    """Send verification email for every newly created user with an email address."""
    if not created or not instance.email:
        return

    try:
        from auth_app.views import send_verification_email

        profile, _ = UserProfile.objects.get_or_create(user=instance)
        send_verification_email(instance, profile)
    except Exception:
        logger.exception("Failed to send verification email for user_id=%s", instance.pk)
