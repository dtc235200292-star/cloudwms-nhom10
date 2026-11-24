import csv
import json
import re
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import OrderForm, ProductForm, StockImportForm
from .models import Category, Order, Product, StockHistory


def is_admin_user(user):
    return user.is_authenticated and user.is_staff


def home(request):
    products_qs = Product.objects.select_related("category").filter(status="active").order_by("-created_at")
    low_stock_count = products_qs.filter(quantity__lte=5).count()
    products_list = list(products_qs)

    # Gộp trùng danh mục theo tên chuẩn hóa (loại bỏ trùng "phụ kiện mạng" / "Phụ kiện mạng")
    unique_categories = []
    seen_names = set()
    for cat in Category.objects.all().order_by("id"):
        norm_name = " ".join(cat.name.strip().lower().split())
        if norm_name not in seen_names:
            seen_names.add(norm_name)
            unique_categories.append({
                "key": norm_name,
                "name": cat.name.strip()[:1].upper() + cat.name.strip()[1:] if cat.name.strip() else cat.name,
            })

    context = {
        "products": products_list,
        "featured": products_list[0] if products_list else None,
        "categories": unique_categories,
        "total_products": products_qs.count(),
        "total_stock": products_qs.aggregate(total=Sum("quantity"))["total"] or 0,
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
    products = Product.objects.select_related("category", "supplier").all()
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
            if product.quantity > 0:
                StockHistory.objects.create(
                    product=product,
                    action="import",
                    quantity=product.quantity,
                    note="Tồn kho khởi tạo khi thêm sản phẩm mới",
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
            note = form.cleaned_data.get("note", "").strip() or "Nhập bổ sung tồn kho"

            with transaction.atomic():
                product.quantity += quantity
                product.save()
                StockHistory.objects.create(
                    product=product,
                    action="import",
                    quantity=quantity,
                    note=note,
                )
            messages.success(request, f"Đã nhập thêm {quantity} sản phẩm cho '{product.name}'.")
            return redirect("stock_history_list")
    else:
        initial_data = {}
        product_id = request.GET.get("product")
        if product_id and product_id.isdigit():
            initial_data["product"] = int(product_id)
        form = StockImportForm(initial=initial_data)
    return render(request, "inventory/form.html", {"form": form, "title": "Nhập hàng vào kho"})


@login_required
@user_passes_test(is_admin_user)
def stock_history_list(request):
    histories = StockHistory.objects.select_related("product").order_by("-created_at")
    return render(request, "inventory/stock_history_list.html", {"histories": histories})


@login_required
@user_passes_test(is_admin_user)
def export_inventory_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="bao_cao_ton_kho_cloudwms.csv"'
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(["Mã SKU", "Tên sản phẩm", "Danh mục", "Nhà cung cấp", "Số lượng tồn", "Đơn giá (VNĐ)", "Giá trị tồn (VNĐ)", "Trạng thái"])

    for p in Product.objects.select_related("category", "supplier").all():
        writer.writerow([
            p.sku,
            p.name,
            p.category.name if p.category else "Chưa phân loại",
            p.supplier.name if p.supplier else "Chưa cập nhật",
            p.quantity,
            p.price,
            p.price * p.quantity,
            p.get_status_display(),
        ])
    return response


@login_required
@user_passes_test(is_admin_user)
def export_history_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="so_cai_lich_su_kho_cloudwms.csv"'
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(["Mã phiếu", "Thời gian", "Mã SKU", "Sản phẩm", "Loại giao dịch", "Số lượng", "Ghi chú"])

    for h in StockHistory.objects.select_related("product").order_by("-created_at"):
        writer.writerow([
            h.id,
            timezone.localtime(h.created_at).strftime("%d/%m/%Y %H:%M"),
            h.product.sku,
            h.product.name,
            h.get_action_display(),
            h.quantity,
            h.note or "",
        ])
    return response


@login_required
@user_passes_test(is_admin_user)
def dashboard(request):
    products = Product.objects.select_related("category").all()
    out_of_stock_count = products.filter(quantity=0).count()
    low_stock_products = products.filter(quantity__lte=5).order_by("quantity", "name")

    total_stock = products.aggregate(total=Sum("quantity"))["total"] or 0
    total_value = sum((p.price * p.quantity for p in products), Decimal("0"))

    total_imported = (
        StockHistory.objects.filter(action="import").aggregate(total=Sum("quantity"))["total"] or 0
    )
    total_exported = (
        StockHistory.objects.filter(action="export").aggregate(total=Sum("quantity"))["total"] or 0
    )

    approved_orders_qs = Order.objects.filter(status="approved").select_related("product")
    approved_revenue = sum((o.total_price for o in approved_orders_qs), Decimal("0"))

    pending_orders = Order.objects.filter(status="pending").count()
    approved_orders = approved_orders_qs.count()
    rejected_orders = Order.objects.filter(status="rejected").count()

    # Dữ liệu biểu đồ cột: Tồn kho theo từng nhóm danh mục (gộp trùng tên)
    cat_map = {}
    for p in products:
        cat_name = p.category.name.strip() if p.category and p.category.name.strip() else "Chưa phân loại"
        norm_key = " ".join(cat_name.lower().split())
        if norm_key not in cat_map:
            display_name = cat_name[:1].upper() + cat_name[1:]
            cat_map[norm_key] = {"name": display_name, "qty": 0}
        cat_map[norm_key]["qty"] += p.quantity

    cat_labels = [v["name"] for v in cat_map.values()]
    cat_quantities = [v["qty"] for v in cat_map.values()]

    top_products = (
        approved_orders_qs.values("product__sku", "product__name")
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")[:5]
    )

    recent_orders = Order.objects.select_related("user", "product").order_by("-created_at")[:6]

    context = {
        "total_products": products.count(),
        "out_of_stock_count": out_of_stock_count,
        "total_stock": total_stock,
        "total_imported": total_imported,
        "total_exported": total_exported,
        "total_value": total_value,
        "approved_revenue": approved_revenue,
        "pending_orders": pending_orders,
        "approved_orders": approved_orders,
        "rejected_orders": rejected_orders,
        "cat_labels": json.dumps(cat_labels, ensure_ascii=False),
        "cat_quantities": json.dumps(cat_quantities),
        "recent_orders": recent_orders,
        "top_products": top_products,
        "low_stock_products": low_stock_products,
        "recent_histories": StockHistory.objects.select_related("product").order_by("-created_at")[:6],
    }
    return render(request, "inventory/dashboard.html", context)


@login_required
def order_create(request):
    if request.user.is_staff:
        messages.info(request, "Tài khoản Quản trị viên chỉ duyệt đơn, không đặt hàng như khách hàng.")
        return redirect("order_list")

    products = Product.objects.filter(status="active", quantity__gt=0)

    if request.method == "POST":
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            if order.quantity > order.product.quantity:
                messages.error(
                    request,
                    f"Sản phẩm '{order.product.name}' chỉ còn tối đa {order.product.quantity} sản phẩm trong kho.",
                )
            else:
                order.user = request.user
                order.status = "pending"
                order.save()
                messages.success(request, f"Đã gửi đơn đặt hàng #{order.id} thành công! Chờ quản trị viên duyệt.")
                return redirect("my_orders")
    else:
        form = OrderForm()
        form.fields["product"].queryset = products

    return render(request, "inventory/order_form.html", {"form": form, "products": products})


@login_required
def my_orders(request):
    orders = Order.objects.filter(user=request.user).select_related("product").order_by("-created_at")
    return render(request, "inventory/my_orders.html", {"orders": orders})


@login_required
@user_passes_test(is_admin_user)
def order_list(request):
    orders = Order.objects.select_related("user", "product").order_by("-created_at")
    return render(request, "inventory/order_list.html", {"orders": orders})


@login_required
@user_passes_test(is_admin_user)
def order_approve(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST":
        if order.status != "pending":
            messages.warning(request, f"Đơn hàng #{order.id} đã được xử lý trước đó.")
            return redirect("order_list")

        if order.product.quantity < order.quantity:
            messages.error(
                request,
                f"Không đủ tồn kho cho '{order.product.name}' (Còn: {order.product.quantity}, Cần: {order.quantity}).",
            )
            return redirect("order_list")

        with transaction.atomic():
            product = order.product
            product.quantity -= order.quantity
            product.save()

            StockHistory.objects.create(
                product=product,
                action="export",
                quantity=order.quantity,
                note=f"Xuất kho theo đơn đặt hàng #{order.id} ({order.user.username})",
            )

            order.status = "approved"
            order.save()

        messages.success(request, f"Đã duyệt đơn #{order.id} và tự động trừ tồn kho thành công!")
    return redirect("order_list")


@login_required
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not (request.user.is_staff or order.user == request.user):
        messages.error(request, "Bạn không có quyền hủy đơn hàng này.")
        return redirect("home")

    if request.method == "POST":
        if order.status == "pending":
            order.status = "rejected"
            order.save()
            messages.success(request, f"Đã hủy/từ chối đơn hàng #{order.id}.")
        else:
            messages.warning(request, "Chỉ có thể hủy đơn hàng đang ở trạng thái Chờ duyệt.")

    if request.user.is_staff:
        return redirect("order_list")
    return redirect("my_orders")


@login_required
def order_invoice(request, pk):
    order = get_object_or_404(Order.objects.select_related("user", "product"), pk=pk)
    if not (request.user.is_staff or order.user == request.user):
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
