import csv
from datetime import timedelta
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Q, Sum, F
from django.utils import timezone
from .models import Category, Product, Order, StockHistory
from .forms import ProductForm, OrderForm


def is_admin(user):
    return user.is_authenticated and user.is_staff


def home(request):
    q = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "").strip()

    products = Product.objects.select_related("category").all().order_by("-id")
    categories = Category.objects.all().order_by("name")

    if selected_category:
        products = products.filter(category_id=selected_category)

    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))

    return render(request, "inventory/home.html", {
        "products": products,
        "categories": categories,
        "q": q,
        "selected_category": selected_category,
    })


@login_required
@user_passes_test(is_admin)
def dashboard(request):
    total_products = Product.objects.count()
    total_stock = Product.objects.aggregate(total=Sum("quantity"))["total"] or 0
    out_of_stock_count = Product.objects.filter(quantity=0).count()
    low_stock_products = Product.objects.filter(quantity__lte=5).order_by("quantity")

    pending_orders = Order.objects.filter(status="pending").count()
    approved_orders = Order.objects.filter(status="approved").count()
    rejected_orders = Order.objects.filter(status="rejected").count()

    total_imported = StockHistory.objects.filter(action="import").aggregate(s=Sum("quantity"))["s"] or 0
    total_exported = StockHistory.objects.filter(action="export").aggregate(s=Sum("quantity"))["s"] or 0

    total_value = Product.objects.aggregate(
        val=Sum(F("quantity") * F("price"))
    )["val"] or 0

    approved_revenue = Order.objects.filter(status="approved").aggregate(
        rev=Sum(F("quantity") * F("product__price"))
    )["rev"] or 0

    categories = Category.objects.all()
    cat_labels = []
    cat_quantities = []
    for cat in categories:
        cat_labels.append(cat.name)
        qty = Product.objects.filter(category=cat).aggregate(s=Sum("quantity"))["s"] or 0
        cat_quantities.append(qty)

    top_products = (
        Order.objects.filter(status="approved")
        .values("product__name", "product__sku")
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")[:5]
    )

    recent_orders = Order.objects.select_related("product", "user").order_by("-created_at")[:6]
    recent_histories = StockHistory.objects.select_related("product").order_by("-created_at")[:8]

    return render(request, "inventory/dashboard.html", {
        "total_products": total_products,
        "total_stock": total_stock,
        "out_of_stock_count": out_of_stock_count,
        "low_stock_products": low_stock_products,
        "pending_orders": pending_orders,
        "approved_orders": approved_orders,
        "rejected_orders": rejected_orders,
        "total_imported": total_imported,
        "total_exported": total_exported,
        "total_value": total_value,
        "approved_revenue": approved_revenue,
        "cat_labels": cat_labels,
        "cat_quantities": cat_quantities,
        "top_products": top_products,
        "recent_orders": recent_orders,
        "recent_histories": recent_histories,
    })


@login_required
@user_passes_test(is_admin)
def export_inventory_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="bao_cao_ton_kho_cloudwms.csv"'

    writer = csv.writer(response)
    writer.writerow(["Mã SKU", "Tên sản phẩm", "Danh mục", "Số lượng tồn", "Đơn giá (VNĐ)", "Tổng giá trị (VNĐ)", "Trạng thái"])

    products = Product.objects.select_related("category").all().order_by("sku")
    for p in products:
        status = "Sẵn hàng" if p.quantity > 10 else ("Sắp hết" if p.quantity > 0 else "Tạm hết")
        writer.writerow([
            p.sku,
            p.name,
            p.category.name if p.category else "Chưa phân loại",
            p.quantity,
            int(p.price),
            int(p.quantity * p.price),
            status,
        ])

    return response


@login_required
def product_list(request):
    q = request.GET.get("q", "").strip()
    products = Product.objects.select_related("category").all().order_by("-id")
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    return render(request, "inventory/product_list.html", {"products": products, "q": q})


@login_required
@user_passes_test(is_admin)
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
                    note="Nhập tồn kho ban đầu khi tạo sản phẩm mới"
                )
            messages.success(request, "Thêm sản phẩm mới thành công!")
            return redirect("product_list")
    else:
        form = ProductForm()
    return render(request, "inventory/product_form.html", {"form": form, "title": "Thêm sản phẩm mới"})


@login_required
@user_passes_test(is_admin)
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if "quantity" in form.fields:
            form.fields["quantity"].disabled = True
        if form.is_valid():
            form.save()
            messages.success(request, "Đã cập nhật thông tin sản phẩm. Để thay đổi tồn kho, vui lòng lập Phiếu Nhập Kho.")
            return redirect("product_list")
    else:
        form = ProductForm(instance=product)
        if "quantity" in form.fields:
            form.fields["quantity"].disabled = True
            form.fields["quantity"].help_text = "Khóa chỉnh sửa trực tiếp — Vui lòng dùng chức năng Lập Phiếu Nhập Kho để cộng tồn kho."
    return render(request, "inventory/product_form.html", {"form": form, "title": "Cập nhật thông tin sản phẩm"})


@login_required
@user_passes_test(is_admin)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()
        messages.success(request, "Đã xóa sản phẩm khỏi kho.")
        return redirect("product_list")
    return render(request, "inventory/product_confirm_delete.html", {"product": product})


@login_required
@user_passes_test(is_admin)
def stock_import(request):
    """Chức năng Lập Phiếu Nhập Kho chuyên biệt kèm thông tin Nhà cung cấp & Mã lô"""
    products = Product.objects.select_related("category").all().order_by("name")
    selected_product_id = request.GET.get("product", "").strip()

    if request.method == "POST":
        product_id = request.POST.get("product_id")
        supplier_name = request.POST.get("supplier_name", "").strip()
        batch_code = request.POST.get("batch_code", "").strip()
        note = request.POST.get("note", "").strip()
        try:
            qty = int(request.POST.get("quantity", 0))
        except ValueError:
            qty = 0

        if not product_id or qty <= 0:
            messages.error(request, "Vui lòng chọn sản phẩm và nhập số lượng nhập kho lớn hơn 0.")
            return redirect("stock_import")

        product = get_object_or_404(Product, pk=product_id)
        old_qty = product.quantity
        product.quantity += qty
        product.save()

        details = []
        if batch_code:
            details.append(f"Lô: {batch_code}")
        if supplier_name:
            details.append(f"NCC: {supplier_name}")
        if note:
            details.append(note)
        full_note = " | ".join(details) if details else f"Phiếu nhập kho (+{qty}) bởi {request.user.username}"

        StockHistory.objects.create(
            product=product,
            action="import",
            quantity=qty,
            note=full_note
        )

        messages.success(
            request,
            f"Nhập kho thành công +{qty} '{product.name}' (Tồn cũ: {old_qty} → Tồn mới: {product.quantity})."
        )
        return redirect("stock_history_list")

    return render(request, "inventory/stock_import.html", {
        "products": products,
        "selected_product_id": selected_product_id,
    })


@login_required
@user_passes_test(is_admin)
def stock_history_list(request):
    """Trang Sổ Cái Lịch Sử Nhập/Xuất Kho có bộ lọc toàn hệ thống"""
    action_filter = request.GET.get("action", "").strip()
    product_filter = request.GET.get("product", "").strip()
    q = request.GET.get("q", "").strip()

    histories = StockHistory.objects.select_related("product").all().order_by("-created_at")
    products = Product.objects.all().order_by("name")

    if action_filter in ["import", "export"]:
        histories = histories.filter(action=action_filter)
    if product_filter:
        histories = histories.filter(product_id=product_filter)
    if q:
        histories = histories.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q) | Q(note__icontains=q)
        )

    total_in = histories.filter(action="import").aggregate(s=Sum("quantity"))["s"] or 0
    total_out = histories.filter(action="export").aggregate(s=Sum("quantity"))["s"] or 0

    return render(request, "inventory/stock_history_list.html", {
        "histories": histories,
        "products": products,
        "action_filter": action_filter,
        "product_filter": product_filter,
        "q": q,
        "total_in": total_in,
        "total_out": total_out,
    })


@login_required
@user_passes_test(is_admin)
def export_history_csv(request):
    """Xuất file CSV Sổ cái lịch sử nhập xuất kho"""
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="so_cai_lich_su_kho_cloudwms.csv"'

    writer = csv.writer(response)
    writer.writerow(["Mã phiếu", "Thời gian", "Loại giao dịch", "Mã SKU", "Tên sản phẩm", "Số lượng", "Diễn giải / Ghi chú"])

    histories = StockHistory.objects.select_related("product").all().order_by("-created_at")
    for h in histories:
        loai = "Nhập kho (+)" if h.action == "import" else "Xuất kho (-)"
        writer.writerow([
            f"GD-{h.id}",
            h.created_at.strftime("%d/%m/%Y %H:%M"),
            loai,
            h.product.sku,
            h.product.name,
            h.quantity,
            h.note,
        ])

    return response


@login_required
def order_create(request):
    initial_data = {}
    product_param = request.GET.get("product")
    if product_param:
        initial_data["product"] = product_param

    if request.method == "POST":
        form = OrderForm(request.POST)
        receiver_name = request.POST.get("receiver_name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        shipping_address = request.POST.get("shipping_address", "").strip()
        delivery_speed = request.POST.get("delivery_speed", "standard").strip()
        extra_note = request.POST.get("extra_note", "").strip()

        if not receiver_name or not phone_number or not shipping_address:
            messages.error(request, "Vui lòng nhập đầy đủ Họ tên người nhận, Số điện thoại và Địa chỉ giao hàng!")
            return render(request, "inventory/order_form.html", {
                "form": form,
                "receiver_name": receiver_name,
                "phone_number": phone_number,
                "shipping_address": shipping_address,
                "delivery_speed": delivery_speed,
                "extra_note": extra_note,
            })

        if form.is_valid():
            order = form.save(commit=False)
            if order.quantity > order.product.quantity:
                messages.error(request, f"Số lượng đặt ({order.quantity}) vượt quá tồn kho hiện tại ({order.product.quantity})!")
            else:
                now_local = timezone.localtime(timezone.now())
                if delivery_speed == "express":
                    eta_time = now_local + timedelta(hours=4)
                    speed_label = "Giao hỏa tốc (2 - 4 giờ)"
                else:
                    eta_time = now_local + timedelta(days=2)
                    speed_label = "Giao tiêu chuẩn (1 - 2 ngày)"

                eta_str = eta_time.strftime("%H:%M ngày %d/%m/%Y")
                shipping_summary = (
                    f"Người nhận: {receiver_name} | SĐT: {phone_number} | "
                    f"Địa chỉ: {shipping_address} | Gói: {speed_label} | "
                    f"Dự kiến giao: {eta_str}"
                )
                if extra_note:
                    shipping_summary += f" | Ghi chú: {extra_note}"

                order.user = request.user
                order.status = "pending"
                if hasattr(order, "note"):
                    order.note = shipping_summary
                order.save()
                messages.success(request, f"Đặt hàng thành công! Thời gian giao dự kiến: {eta_str}.")
                return redirect("my_orders")
    else:
        form = OrderForm(initial=initial_data)

    return render(request, "inventory/order_form.html", {
        "form": form,
        "receiver_name": request.user.get_full_name() or request.user.username,
    })


@login_required
def my_orders(request):
    orders = Order.objects.select_related("product").filter(user=request.user).order_by("-created_at")
    return render(request, "inventory/my_orders.html", {"orders": orders})


@login_required
@user_passes_test(is_admin)
def order_list(request):
    orders = Order.objects.select_related("product", "user").all().order_by("-created_at")
    return render(request, "inventory/order_list.html", {"orders": orders})


@login_required
@user_passes_test(is_admin)
def order_approve(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST" and order.status == "pending":
        if order.product.quantity >= order.quantity:
            order.product.quantity -= order.quantity
            order.product.save()

            order.status = "approved"
            order.save()

            StockHistory.objects.create(
                product=order.product,
                action="export",
                quantity=order.quantity,
                note=f"Xuất kho theo đơn #{order.id} của {order.user.username}"
            )
            messages.success(request, f"Đã duyệt đơn #{order.id} và trừ kho thành công.")
        else:
            messages.error(request, f"Không đủ hàng trong kho để duyệt đơn #{order.id}!")
    return redirect("order_list")


@login_required
@user_passes_test(is_admin)
def order_reject(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST" and order.status == "pending":
        order.status = "rejected"
        order.save()
        messages.warning(request, f"Đã từ chối đơn #{order.id}.")
    return redirect("order_list")


@login_required
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status != "pending":
        messages.warning(request, "Chỉ có thể hủy đơn hàng đang ở trạng thái Chờ duyệt.")
        return redirect("my_orders")

    if request.method == "POST":
        order.status = "rejected"
        order.save()
        messages.info(request, f"Bạn đã hủy đơn hàng #{order.id} thành công.")

    return redirect("my_orders")


@login_required
def order_invoice(request, pk):
    if request.user.is_staff:
        order = get_object_or_404(Order, pk=pk)
    else:
        order = get_object_or_404(Order, pk=pk, user=request.user)

    total_amount = order.quantity * order.product.price
    return render(request, "inventory/order_invoice.html", {
        "order": order,
        "total_amount": total_amount,
    })
