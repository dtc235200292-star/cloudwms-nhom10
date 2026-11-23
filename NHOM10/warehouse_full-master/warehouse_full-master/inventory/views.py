from datetime import timedelta
from decimal import Decimal
import re

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import OrderForm, ProductForm, StockImportForm
from .models import Order, OrderItem, Product, StockHistory


def is_admin_user(user):
    return user.is_authenticated and user.is_staff


def home(request):
    products = Product.objects.all()
    low_stock_count = products.filter(stock__lt=10).count()
    context = {
        "products": products[:8],
        "total_products": products.count(),
        "total_stock": products.aggregate(total=Sum("stock"))["total"] or 0,
        "low_stock_count": low_stock_count,
    }
    return render(request, "inventory/home.html", context)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not username or not password:
            messages.error(request, "Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.")
        elif password != confirm_password:
            messages.error(request, "Mật khẩu xác nhận không khớp.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Tên đăng nhập đã tồn tại. Vui lòng chọn tên khác.")
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            user.is_staff = False
            user.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Đăng ký tài khoản khách hàng thành công!")
            return redirect("home")

    return render(request, "accounts/register.html")


def phone_otp_login(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        raw_phone = request.POST.get("phone", "").strip()
        otp_code = request.POST.get("otp", "").strip()
        digits = re.sub(r"\D", "", raw_phone)

        if len(digits) < 9 or len(digits) > 12:
            messages.error(request, "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số).")
            return redirect("/accounts/login/")

        if len(otp_code) != 6 or not otp_code.isdigit():
            messages.error(request, "Mã xác thực OTP phải gồm đúng 6 chữ số.")
            return redirect("/accounts/login/")

        username = f"khach_{digits}"
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": f"Khách hàng ({digits[-4:]})",
                "is_staff": False,
            },
        )
        if created:
            user.set_unusable_password()
            user.save()

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Xác thực OTP thành công! Chào mừng {user.username}.")
        return redirect("home")

    return redirect("/accounts/login/")


def google_login_entry(request):
    if request.user.is_authenticated:
        return redirect("home")

    try:
        from allauth.socialaccount.models import SocialApp

        google_app_exists = SocialApp.objects.filter(provider="google").exists()
    except Exception:
        google_app_exists = False

    if google_app_exists:
        return redirect("/accounts/google/login/")

    messages.info(
        request,
        "Tính năng Google OAuth đang ở chế độ chờ cấu hình Client ID trên Render. Bạn có thể đăng nhập bằng Tài khoản hoặc Số điện thoại (OTP).",
    )
    return redirect("/accounts/login/")


def product_list(request):
    products = Product.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(name__icontains=q) | products.filter(sku__icontains=q)
    return render(request, "inventory/product_list.html", {"products": products, "q": q})


@login_required
@user_passes_test(is_admin_user)
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            if product.stock > 0:
                StockHistory.objects.create(
                    product=product,
                    action="IN",
                    quantity=product.stock,
                    note="Tồn kho khởi tạo khi thêm sản phẩm mới",
                    created_by=request.user,
                )
            messages.success(request, f"Đã thêm sản phẩm '{product.name}' thành công.")
            return redirect("product_list")
    else:
        form = ProductForm()
    return render(request, "inventory/form.html", {"form": form, "title": "Thêm sản phẩm mới"})


@login_required
@user_passes_test(is_admin_user)
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật sản phẩm '{product.name}'.")
            return redirect("product_list")
    else:
        form = ProductForm(instance=product)
    return render(request, "inventory/form.html", {"form": form, "title": f"Chỉnh sửa: {product.name}"})


@login_required
@user_passes_test(is_admin_user)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        name = product.name
        product.delete()
        messages.success(request, f"Đã xóa sản phẩm '{name}'.")
        return redirect("product_list")
    return render(request, "inventory/confirm_delete.html", {"product": product})


@login_required
@user_passes_test(is_admin_user)
def stock_import(request):
    if request.method == "POST":
        form = StockImportForm(request.POST)
        if form.is_valid():
            product = form.cleaned_data["product"]
            quantity = form.cleaned_data["quantity"]
            batch_code = form.cleaned_data.get("batch_code", "").strip()
            supplier = form.cleaned_data.get("supplier", "").strip()
            note = form.cleaned_data.get("note", "").strip()

            detail_parts = []
            if batch_code:
                detail_parts.append(f"Lô: {batch_code}")
            if supplier:
                detail_parts.append(f"NCC: {supplier}")
            if note:
                detail_parts.append(note)
            full_note = " | ".join(detail_parts) if detail_parts else "Nhập bổ sung tồn kho"

            with transaction.atomic():
                product.stock += quantity
                product.save()
                StockHistory.objects.create(
                    product=product,
                    action="IN",
                    quantity=quantity,
                    note=full_note,
                    created_by=request.user,
                )
            messages.success(request, f"Đã nhập thêm {quantity} {product.unit} cho '{product.name}'.")
            return redirect("stock_history_list")
    else:
        form = StockImportForm()
    return render(request, "inventory/form.html", {"form": form, "title": "Nhập hàng vào kho"})


@login_required
@user_passes_test(is_admin_user)
def stock_history_list(request):
    histories = StockHistory.objects.select_related("product", "created_by").all()
    return render(request, "inventory/stock_history_list.html", {"histories": histories})


@login_required
@user_passes_test(is_admin_user)
def dashboard(request):
    products = Product.objects.all()
    low_stock_products = products.filter(stock__lt=10)

    total_stock_value = sum((p.price * p.stock for p in products), Decimal("0"))
    approved_orders = Order.objects.filter(status="APPROVED")
    total_revenue = sum((o.total_amount for o in approved_orders), Decimal("0"))

    pending_orders_count = Order.objects.filter(status="PENDING").count()
    approved_orders_count = approved_orders.count()
    cancelled_orders_count = Order.objects.filter(status="CANCELLED").count()

    today = timezone.now().date()
    chart_labels = []
    chart_in = []
    chart_out = []

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        chart_labels.append(day.strftime("%d/%m"))
        in_qty = (
            StockHistory.objects.filter(action="IN", created_at__date=day).aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        out_qty = (
            StockHistory.objects.filter(action="OUT", created_at__date=day).aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        chart_in.append(in_qty)
        chart_out.append(out_qty)

    context = {
        "total_products": products.count(),
        "total_stock": products.aggregate(total=Sum("stock"))["total"] or 0,
        "total_stock_value": total_stock_value,
        "total_revenue": total_revenue,
        "low_stock_products": low_stock_products,
        "low_stock_count": low_stock_products.count(),
        "pending_orders_count": pending_orders_count,
        "approved_orders_count": approved_orders_count,
        "cancelled_orders_count": cancelled_orders_count,
        "chart_labels": chart_labels,
        "chart_in": chart_in,
        "chart_out": chart_out,
        "recent_histories": StockHistory.objects.select_related("product")[:6],
    }
    return render(request, "inventory/dashboard.html", context)


@login_required
def order_create(request):
    if request.user.is_staff:
        messages.info(request, "Tài khoản Quản trị viên chỉ duyệt đơn, không đặt hàng như khách hàng.")
        return redirect("order_list")

    products = Product.objects.filter(stock__gt=0)

    if request.method == "POST":
        form = OrderForm(request.POST)
        selected_items = []
        for p in products:
            qty_str = request.POST.get(f"qty_{p.id}", "0").strip()
            try:
                qty = int(qty_str)
            except ValueError:
                qty = 0
            if qty > 0:
                if qty > p.stock:
                    messages.error(request, f"Sản phẩm '{p.name}' chỉ còn tối đa {p.stock} {p.unit} trong kho.")
                    return render(request, "inventory/order_form.html", {"form": form, "products": products})
                selected_items.append((p, qty))

        if not selected_items:
            messages.error(request, "Vui lòng chọn số lượng lớn hơn 0 cho ít nhất một sản phẩm.")
            return render(request, "inventory/order_form.html", {"form": form, "products": products})

        if form.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)
                order.customer = request.user
                order.status = "PENDING"
                order.save()

                for p, qty in selected_items:
                    OrderItem.objects.create(
                        order=order,
                        product=p,
                        quantity=qty,
                        unit_price=p.price,
                    )

            messages.success(request, f"Đã gửi đơn đặt hàng #{order.id} thành công! Chờ quản trị viên duyệt.")
            return redirect("my_orders")
    else:
        form = OrderForm(initial={"customer_name": request.user.get_full_name() or request.user.username})

    return render(request, "inventory/order_form.html", {"form": form, "products": products})


@login_required
def my_orders(request):
    orders = Order.objects.filter(customer=request.user).prefetch_related("items__product")
    return render(request, "inventory/my_orders.html", {"orders": orders})


@login_required
@user_passes_test(is_admin_user)
def order_list(request):
    orders = Order.objects.select_related("customer").prefetch_related("items__product").all()
    return render(request, "inventory/order_list.html", {"orders": orders})


@login_required
@user_passes_test(is_admin_user)
def order_approve(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST":
        if order.status != "PENDING":
            messages.warning(request, f"Đơn hàng #{order.id} đã được xử lý trước đó.")
            return redirect("order_list")

        items = list(order.items.select_related("product"))
        for item in items:
            if item.product.stock < item.quantity:
                messages.error(
                    request,
                    f"Không đủ tồn kho cho '{item.product.name}' (Còn: {item.product.stock}, Cần: {item.quantity}).",
                )
                return redirect("order_list")

        with transaction.atomic():
            for item in items:
                product = item.product
                product.stock -= item.quantity
                product.save()

                StockHistory.objects.create(
                    product=product,
                    action="OUT",
                    quantity=item.quantity,
                    note=f"Xuất kho theo đơn đặt hàng #{order.id} ({order.customer_name})",
                    created_by=request.user,
                )

            order.status = "APPROVED"
            order.save()

        messages.success(request, f"Đã duyệt đơn #{order.id} và tự động trừ tồn kho thành công!")
    return redirect("order_list")


@login_required
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not (request.user.is_staff or order.customer == request.user):
        messages.error(request, "Bạn không có quyền hủy đơn hàng này.")
        return redirect("home")

    if request.method == "POST":
        if order.status == "PENDING":
            order.status = "CANCELLED"
            order.save()
            messages.success(request, f"Đã hủy đơn hàng #{order.id}.")
        else:
            messages.warning(request, "Chỉ có thể hủy đơn hàng đang ở trạng thái Chờ duyệt.")

    if request.user.is_staff:
        return redirect("order_list")
    return redirect("my_orders")


@login_required
def order_invoice(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items__product"), pk=pk)
    if not (request.user.is_staff or order.customer == request.user):
        messages.error(request, "Bạn không có quyền xem phiếu xuất kho của đơn này.")
        return redirect("home")
    return render(request, "inventory/order_invoice.html", {"order": order})


def password_reset_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    verified_user = None
    step = "identify"

    if request.method == "POST":
        action = request.POST.get("action")
        identifier = request.POST.get("identifier", "").strip()

        if action == "verify":
            user = (
                User.objects.filter(username=identifier).first()
                or User.objects.filter(email__iexact=identifier).exclude(email="").first()
            )
            if user:
                verified_user = user
                step = "reset"
            else:
                messages.error(request, "Không tìm thấy tài khoản hoặc email tương ứng trong hệ thống.")
        elif action == "reset":
            user_id = request.POST.get("user_id")
            new_pass = request.POST.get("new_password", "")
            confirm_pass = request.POST.get("confirm_password", "")
            user = User.objects.filter(id=user_id).first()

            if not user:
                messages.error(request, "Phiên khôi phục không hợp lệ. Vui lòng thử lại.")
            elif len(new_pass) < 6:
                messages.error(request, "Mật khẩu mới phải có ít nhất 6 ký tự.")
                verified_user = user
                step = "reset"
            elif new_pass != confirm_pass:
                messages.error(request, "Mật khẩu xác nhận không khớp.")
                verified_user = user
                step = "reset"
            else:
                user.set_password(new_pass)
                user.save()
                messages.success(
                    request,
                    f"Đã cập nhật mật khẩu mới cho tài khoản '{user.username}'. Vui lòng đăng nhập lại.",
                )
                return redirect("/accounts/login/")

    return render(
        request,
        "accounts/password_reset.html",
        {
            "step": step,
            "verified_user": verified_user,
        },
    )
