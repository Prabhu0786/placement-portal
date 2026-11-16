import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import PasswordResetOTP

User = get_user_model()
OTP_SESSION_KEY = "password_reset_otp_id"
OTP_LIFETIME_MINUTES = 5
OTP_RESEND_SECONDS = 60
MAX_OTP_ATTEMPTS = 5


def _client_ip(request):
    # Use REMOTE_ADDR; do not trust arbitrary forwarded headers.
    return request.META.get("REMOTE_ADDR") or None


@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not email:
            return render(request, "accounts/password_reset_otp_request.html",
                          {"error": "Please enter your registered email address."})

        now = timezone.now()
        ip = _client_ip(request)

        # A cooldown is enforced for the email and the requesting IP.
        recent = PasswordResetOTP.objects.filter(
            created_at__gte=now - timedelta(seconds=OTP_RESEND_SECONDS)
        )
        if recent.filter(email__iexact=email).exists() or (
            ip and recent.filter(request_ip=ip).exists()
        ):
            request.session["password_reset_email"] = email
            return redirect("password_reset_otp_sent")

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        otp = f"{secrets.randbelow(1_000_000):06d}"

        # Invalidate previous active challenges for this email.
        PasswordResetOTP.objects.filter(
            email__iexact=email, used_at__isnull=True
        ).update(used_at=now)

        record = PasswordResetOTP.objects.create(
            user=user,
            email=email,
            otp_hash=make_password(otp),
            expires_at=now + timedelta(minutes=OTP_LIFETIME_MINUTES),
            request_ip=ip,
        )

        # Unknown email addresses get the same page, but no email is sent.
        if user:
            try:
                send_mail(
                    subject="Your Placement Portal password reset OTP",
                    message=(
                        f"Your password reset OTP is {otp}.\n\n"
                        "It expires in 5 minutes. Do not share this code with anyone.\n"
                        "If you did not request this, you can ignore this email."
                    ),
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception:
                record.used_at = now
                record.save(update_fields=["used_at"])
                return render(
                    request,
                    "accounts/password_reset_otp_request.html",
                    {"error": "We couldn't send the email right now. Please try again later."},
                )

        request.session["password_reset_email"] = email
        return redirect("password_reset_otp_sent")

    return render(request, "accounts/password_reset_otp_request.html")


def password_reset_otp_sent(request):
    # This page intentionally does not reveal whether an account exists.
    return render(request, "accounts/password_reset_otp_sent.html")


@require_http_methods(["GET", "POST"])
def password_reset_verify_otp(request):
    email = request.session.get("password_reset_email")
    if not email:
        return redirect("password_reset")

    if request.method == "POST":
        submitted_otp = request.POST.get("otp", "").strip()
        now = timezone.now()

        with transaction.atomic():
            record = (
                PasswordResetOTP.objects.select_for_update()
                .filter(
                    email__iexact=email,
                    user__isnull=False,
                    used_at__isnull=True,
                    verified_at__isnull=True,
                    expires_at__gt=now,
                )
                .order_by("-created_at")
                .first()
            )

            if not record or record.attempts >= MAX_OTP_ATTEMPTS:
                return render(
                    request, "accounts/password_reset_otp_verify.html",
                    {"error": "This OTP is invalid or expired. Please request a new one."},
                )

            if not submitted_otp.isdigit() or len(submitted_otp) != 6 or not check_password(
                submitted_otp, record.otp_hash
            ):
                record.attempts += 1
                if record.attempts >= MAX_OTP_ATTEMPTS:
                    record.used_at = now
                record.save(update_fields=["attempts", "used_at"])
                remaining = max(0, MAX_OTP_ATTEMPTS - record.attempts)
                return render(
                    request, "accounts/password_reset_otp_verify.html",
                    {"error": f"Incorrect OTP. Attempts remaining: {remaining}."},
                )

            record.verified_at = now
            record.save(update_fields=["verified_at"])
            request.session[OTP_SESSION_KEY] = record.pk

        return redirect("password_reset_new_password")

    return render(request, "accounts/password_reset_otp_verify.html")


@require_http_methods(["GET", "POST"])
def password_reset_new_password(request):
    record_id = request.session.get(OTP_SESSION_KEY)
    if not record_id:
        return redirect("password_reset")

    record = PasswordResetOTP.objects.filter(
        pk=record_id,
        user__isnull=False,
        verified_at__isnull=False,
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).select_related("user").first()

    if not record:
        request.session.pop(OTP_SESSION_KEY, None)
        request.session.pop("password_reset_email", None)
        return redirect("password_reset")

    if request.method == "POST":
        password1 = request.POST.get("new_password1", "")
        password2 = request.POST.get("new_password2", "")
        if password1 != password2:
            return render(request, "accounts/password_reset_new_password.html",
                          {"error": "The passwords do not match."})
        try:
            validate_password(password1, user=record.user)
        except ValidationError as exc:
            return render(request, "accounts/password_reset_new_password.html",
                          {"error": " ".join(exc.messages)})

        with transaction.atomic():
            locked = PasswordResetOTP.objects.select_for_update().get(pk=record.pk)
            if locked.used_at or not locked.verified_at or locked.expires_at <= timezone.now():
                request.session.pop(OTP_SESSION_KEY, None)
                return redirect("password_reset")
            user = User.objects.select_for_update().get(pk=locked.user_id)
            user.set_password(password1)
            user.save(update_fields=["password"])
            locked.used_at = timezone.now()
            locked.save(update_fields=["used_at"])

        request.session.pop(OTP_SESSION_KEY, None)
        request.session.pop("password_reset_email", None)
        return redirect("password_reset_complete_otp")

    return render(request, "accounts/password_reset_new_password.html")


def password_reset_complete_otp(request):
    return render(request, "accounts/password_reset_complete_otp.html")
