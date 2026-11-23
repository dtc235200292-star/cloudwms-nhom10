import json
import os
import secrets
import urllib.parse
import urllib.request

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.urls import reverse


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Đăng ký tài khoản thành công!")
            return redirect("home")
    else:
        form = UserCreationForm()

    return render(request, "accounts/register.html", {"form": form})


def google_login(request):
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        messages.info(
            request,
            "Tính năng Google OAuth đang ở chế độ chờ cấu hình Client ID trên Render. Bạn có thể đăng nhập bằng Tài khoản hoặc Số điện thoại (OTP).",
        )
        return redirect("login")

    state = secrets.token_urlsafe(24)
    request.session["google_oauth_state"] = state

    redirect_uri = request.build_absolute_uri(reverse("google_callback"))
    if "onrender.com" in redirect_uri and redirect_uri.startswith("http://"):
        redirect_uri = "https://" + redirect_uri[len("http://") :]

    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


def google_callback(request):
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        messages.error(request, "Thiếu cấu hình GOOGLE_CLIENT_ID hoặc GOOGLE_CLIENT_SECRET trên hệ thống.")
        return redirect("login")

    error = request.GET.get("error")
    if error:
        messages.warning(request, "Bạn đã hủy đăng nhập với Google.")
        return redirect("login")

    state = request.GET.get("state")
    saved_state = request.session.pop("google_oauth_state", None)
    if not state or state != saved_state:
        messages.error(request, "Phiên xác thực Google không hợp lệ. Vui lòng thử lại.")
        return redirect("login")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "Không nhận được mã xác thực từ Google.")
        return redirect("login")

    redirect_uri = request.build_absolute_uri(reverse("google_callback"))
    if "onrender.com" in redirect_uri and redirect_uri.startswith("http://"):
        redirect_uri = "https://" + redirect_uri[len("http://") :]

    # Bước 1: Đổi authorization code lấy access_token
    token_data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")

    try:
        token_req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(token_req, timeout=10) as resp:
            token_json = json.loads(resp.read().decode("utf-8"))

        access_token = token_json.get("access_token")
        if not access_token:
            messages.error(request, "Không lấy được token đăng nhập từ Google.")
            return redirect("login")

        # Bước 2: Lấy thông tin email và họ tên từ Google
        userinfo_req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(userinfo_req, timeout=10) as resp:
            userinfo = json.loads(resp.read().decode("utf-8"))

    except Exception:
        messages.error(request, "Lỗi kết nối đến máy chủ Google. Vui lòng thử lại.")
        return redirect("login")

    email = (userinfo.get("email") or "").strip().lower()
    if not email:
        messages.error(request, "Tài khoản Google không cung cấp địa chỉ email.")
        return redirect("login")

    # Bước 3: Tìm user theo email hoặc tự động tạo mới nếu lần đầu đăng nhập
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        base_username = email.split("@")[0]
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=userinfo.get("given_name", ""),
            last_name=userinfo.get("family_name", ""),
        )
        user.set_unusable_password()
        user.save()

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, f"Đăng nhập thành công với tài khoản {email}!")
    return redirect("home")
