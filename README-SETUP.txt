EMAIL OTP PASSWORD RESET - INTEGRATION

This package replaces the previous email reset-link URLs with an email OTP flow.
It preserves the supplied accounts/models.py models and appends PasswordResetOTP.
It does not replace accounts/views.py or the login template.

COPY THESE FILES:
1. accounts/models.py -> replace your existing accounts/models.py
   (This is your uploaded model file with PasswordResetOTP appended.)
2. accounts/otp_views.py -> add this new file.
3. accounts/urls.py -> replace your existing accounts/urls.py.
4. Copy all five HTML files from accounts/templates/accounts/ into the same
   folder in your project.

LOGIN LINK:
Your login template should link to {% url 'password_reset' %}.
If the previous forgot-password link is already present, it should continue
working because the URL name remains password_reset.

THEN RUN IN PROJECT ROOT:
python manage.py check
python manage.py makemigrations accounts
python manage.py migrate
python manage.py runserver

EMAIL CONFIGURATION:
The OTP email uses Django's configured email backend and DEFAULT_FROM_EMAIL.
For local-only testing, you can temporarily set:
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
The OTP email will print in the terminal; it will not reach an inbox.

For real email delivery, configure a production SMTP provider using environment
variables (EMAIL_HOST, EMAIL_PORT, EMAIL_USE_TLS, EMAIL_HOST_USER,
EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL). Never commit secrets or paste them
into chat. Add the same variables in Vercel Project Settings > Environment
Variables, then redeploy.

SECURITY NOTES:
- OTP is six digits, randomly generated and stored only as a Django password hash.
- Expiry is 5 minutes.
- Maximum 5 verification attempts.
- 60-second resend cooldown per email and per source IP.
- Successful OTP verification is tied to the browser session.
- Passwords are checked using Django's configured password validators.
- Responses do not disclose whether an email is registered.

IMPORTANT:
The 60-second cooldown uses database records. The request IP uses REMOTE_ADDR;
if your deployment sits behind a proxy, configure trusted proxy handling
carefully rather than blindly trusting X-Forwarded-For.
For production, also configure a shared cache or edge-level rate limiting for
broader abuse protection, monitor email delivery, and periodically clean up
old PasswordResetOTP rows. The provided OTP expiry and attempt checks remain
enforced in the database.
