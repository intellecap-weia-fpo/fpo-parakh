import graphene
import graphql_jwt
from graphene import relay
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from graphql_jwt.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings

import fpo.schema


User = get_user_model()


class UserNode(DjangoObjectType):
    class Meta:
        model = User
        exclude = (
            'password', 'is_superuser', 'last_login', 'user_permissions',
            'fpos_created', 'submissions_made', 'submissions_reviewed', 'fpo_verification_reviews',
        )
        filter_fields = {
            'username': ['exact', 'icontains', 'istartswith'],
            'email': ['exact', 'icontains'],
            'first_name': ['exact', 'icontains'],
            'last_name': ['exact', 'icontains'],
            'is_active': ['exact'],
            'is_staff': ['exact'],
        }
        interfaces = (relay.Node, )

    @classmethod
    def get_queryset(cls, queryset, info):
        # Every path to a user (node lookup, foreign keys on other types) ends here:
        # staff see everyone, others only themselves.
        user = info.context.user
        if not user.is_authenticated:
            return queryset.none()
        if user.is_staff or user.is_superuser:
            return queryset
        return queryset.filter(pk=user.pk)


class UserType(graphene.ObjectType):
    id = graphene.ID()
    username = graphene.String()
    email = graphene.String()
    first_name = graphene.String()
    last_name = graphene.String()
    is_active = graphene.Boolean()
    is_staff = graphene.Boolean()


class Query(fpo.schema.Query, graphene.ObjectType):
    hello = graphene.String(default_value="Hi!")
    me = graphene.Field(UserType)

    # Relay fields - Protected
    user = relay.Node.Field(UserNode)
    all_users = DjangoFilterConnectionField(UserNode)

    @login_required
    def resolve_me(self, info):
        user = info.context.user
        return user

    @login_required
    def resolve_user(self, info, **kwargs):
        user = info.context.user
        if not user.is_staff and not user.is_superuser:
            return None
        return relay.Node.get_node_from_global_id(info, kwargs.get('id'))

    @login_required
    def resolve_all_users(self, info, **kwargs):
        user = info.context.user
        if not user.is_staff and not user.is_superuser:
            return User.objects.none()
        return User.objects.all()


class CreateAccount(graphene.Mutation):
    class Arguments:
        username = graphene.String(required=True)
        email = graphene.String(required=True)
        password = graphene.String(required=True)
        first_name = graphene.String()
        last_name = graphene.String()

    user = graphene.Field(UserType)
    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, username, email, password, first_name=None, last_name=None):
        if not settings.ALLOW_SIGNUP:
            return CreateAccount(user=None, success=False, message="Sign up is disabled.")
        username = username.strip().lower()
        email = email.strip().lower()

        try:
            validate_email(email)
            candidate = User(
                username=username,
                email=email,
                first_name=(first_name or '').strip(),
                last_name=(last_name or '').strip(),
            )
            validate_password(password, user=candidate)

            if User.objects.filter(username__iexact=username).exists():
                return CreateAccount(user=None, success=False, message="Username already exists")

            if User.objects.filter(email__iexact=email).exists():
                return CreateAccount(user=None, success=False, message="Email already exists")

            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=candidate.first_name,
                    last_name=candidate.last_name,
                )

            return CreateAccount(user=user, success=True, message="Account created successfully")
        except ValidationError as exc:
            return CreateAccount(user=None, success=False, message=" ".join(exc.messages))
        except IntegrityError:
            return CreateAccount(user=None, success=False, message="An account with these details already exists")
        except Exception:
            return CreateAccount(user=None, success=False, message="Unable to create the account. Please try again.")


class ForgotPassword(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, email):
        try:
            # Check if user exists with this email
            user = User.objects.filter(email=email).first()
            
            if not user:
                # Don't reveal if email exists or not for security
                return ForgotPassword(
                    success=True, 
                    message="If an account exists with this email, a password reset link has been sent."
                )
            
            # Generate password reset token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Create reset URL (you may need to adjust this based on your frontend URL)
            reset_url = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}"
            
            # Send email
            subject = "Password Reset Request"
            message = f"""
            Hello {user.first_name or user.username},
            
            You requested a password reset. Click the link below to reset your password:
            
            {reset_url}
            
            If you didn't request this, please ignore this email.
            
            This link will expire in 24 hours.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            
            return ForgotPassword(
                success=True,
                message="If an account exists with this email, a password reset link has been sent."
            )
            
        except Exception as e:
            return ForgotPassword(
                success=False,
                message="An error occurred while processing your request. Please try again later."
            )


class ResetPassword(graphene.Mutation):
    class Arguments:
        uid = graphene.String(required=True)
        token = graphene.String(required=True)
        new_password = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, uid, token, new_password):
        try:
            from django.utils.http import urlsafe_base64_decode
            
            # Decode the user ID
            try:
                uid = urlsafe_base64_decode(uid).decode()
                user = User.objects.get(pk=uid)
            except (TypeError, ValueError, OverflowError, User.DoesNotExist):
                return ResetPassword(success=False, message="Invalid reset link")
            
            # Check if token is valid
            if not default_token_generator.check_token(user, token):
                return ResetPassword(success=False, message="Invalid or expired reset link")
            
            validate_password(new_password, user=user)
            user.set_password(new_password)
            user.save()
            
            return ResetPassword(success=True, message="Password has been reset successfully")
            
        except ValidationError as exc:
            return ResetPassword(success=False, message=" ".join(exc.messages))
        except Exception:
            return ResetPassword(
                success=False,
                message="An error occurred while resetting your password. Please try again."
            )


class CustomObtainJSONWebToken(graphql_jwt.ObtainJSONWebToken):
    @classmethod
    def mutate(cls, root, info, **kwargs):
        # Convert username to lowercase for case-insensitive authentication
        if 'username' in kwargs:
            kwargs['username'] = kwargs['username'].lower()
        return super().mutate(root, info, **kwargs)


class Mutation(fpo.schema.Mutation, graphene.ObjectType):
    sign_in = CustomObtainJSONWebToken.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()
    logout = graphql_jwt.DeleteJSONWebTokenCookie.Field()
    delete_refresh_token_cookie = graphql_jwt.DeleteRefreshTokenCookie.Field()
    create_account = CreateAccount.Field()
    forgot_password = ForgotPassword.Field()
    reset_password = ResetPassword.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
