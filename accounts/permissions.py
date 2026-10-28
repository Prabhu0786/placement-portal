from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    """Allow only logged-in users whose role is in allowed_roles (BR-1 and BR-2).

    Usage:  @role_required("Student")  or  @role_required("TPO", "Faculty")
    Anonymous users are sent to the login page; wrong-role users get a 403 page.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.role_name not in allowed_roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return login_required(wrapper)

    return decorator
