import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Q, Count, Sum, F

from .models import Product, Order, Category, Supplier, StockHistory
from .forms import ProductForm, OrderForm, CategoryForm, SupplierForm


def is_admin(user):
    return user.is_authenticated and user.is_staff


def home(request):
    q = request.GET.get("q", "").strip()
    cat_id = request.GET.get("category", "")
    products = Product.objects.select_related("category", "supplier").filter(status="active").order_by("-created_at")
    categories = Category.objects.all()

    if q:
        products = products.filter(
            Q(name__icontains=q) |
            Q(sku__icontains=q) |
            Q(category__name__icontains=q)
        )
    if cat_id:
        products = products.filter(category_id=cat_id)

    return render(request, "inventory/home.html", {
        "products": products,
        "categories": categories,
        "q": q,
        "selected_category": cat_id,
    })


@login_required
@user_passes_test(is_admin)
def dashboard(request):
    total_products = Product.objects.count()
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status="pending").count()
    approved_orders = Order.objects.filter(status="approved").count()

    inventory_agg = Product.objects.aggregate(
        total_val=Sum(F("quantity") * F("price")),
        total_items=Sum("quantity")
    )
    total_inventory_value = inventory_agg["total_val"] or 0
    total_stock_items = inventory_agg["total_items"] or 0

    low_stock_products = Product.objects.select_related("category").filter(quantity__lte=5).order_by("quantity")
    recent_orders = Order.objects.select_related("user", "product").order_by("-created_at")[:10]
    recent_histories = StockHistory.objects.select_related("product").order_by("-created_at")[:8]

    order_stats = Order.objects.values("status").annotate(total=Count("id"))
    category_stats = Category.objects.annotate(total_products=Count("products"))

    return render(request, "inventory/dashboard.html", {
        "total_products": total_products,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "approved_orders": approved_orders,
        "total_inventory_value": total_inventory_value,
        "total_stock_items": total_stock_items,
        "low_stock_products": low_stock_products,
        "recent_orders": recent_orders,
        "recent_histories": recent_histories,
        "order_stats": order_stats,
        "category_stats": category_stats,
    })


@login_required
@user_passes_test(is_admin)
def export_inventory_csv(request):
    """Xuất báo cáo tồn kho ra file CSV (mở trực tiếp bằng Excel có tiếng Việt chuẩn UTF-8 BOM)"""
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="bao_cao_ton_kho_nhom10.csv"'

    writer = csv.writer(response)
    writer.writerow(["Mã SKU", "Tên sản phẩm", "Danh mục", "Nhà cung cấp", "Số lượng tồn", "Đơn giá (VNĐ)", "Thành tiền (VNĐ)", "Trạng thái"])

    products = Product.objects.select_related("category", "supplier").all()
    for p in products:
        writer.writerow([
            p.sku,
            p.name,
            p.category.name if p.category else "Chưa phân loại",
            p.supplier.name if p.supplier else "Không có",
            p.quantity,
            p.price,
            p.quantity * p.price,
            p.get_status_display(),
        ])

    return response


@login_required
def product_list(request):
    q = request.GET.get("q", "").strip()
    if request.user.is_staff:
        products = Product.objects.select_related("category", "supplier").all().order_by("-created_at")
    else:
        products = Product.objects.select_related("category", "supplier").filter(status="active").order_by("-created_at")

    if q:
        products = products.filter(
            Q(name__icontains=q) |
            Q(sku__icontains=q) |
            Q(category__name__icontains=q)
        )

    return render(request, "inventory/product_list.html", {
        "products": products,
        "q": q,
    })


@login_required
@user_passes_test(is_admin)
def product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)

    if form.is_valid():
        product = form.save()
        if product.quantity > 0:
            StockHistory.objects.create(
                product=product,
                action="import",
                quantity=product.quantity,
                note="Khởi tạo sản phẩm mới"
            )
        messages.success(request, f"Đã thêm sản phẩm '{product.name}' vào kho.")
        return redirect("product_list")

    return render(request, "inventory/form.html", {
        "form": form,
        "title": "Thêm sản phẩm mới"
    })


@login_required
@user_passes_test(is_admin)
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    old_quantity = product.quantity

    form = ProductForm(request.POST or None, request.FILES or None, instance=product)

    if form.is_valid():
        product = form.save()

        if product.quantity != old_quantity:
            diff = product.quantity - old_quantity
            StockHistory.objects.create(
                product=product,
                action="import" if diff > 0 else "export",
                quantity=abs(diff),
                note=f"Điều chỉnh tồn kho ({old_quantity} → {product.quantity})"
            )

        messages.success(request, f"Đã cập nhật thông tin '{product.name}'.")
        return redirect("product_list")

    return render(request, "inventory/form.html", {
        "form": form,
        "title": "Cập nhật sản phẩm"
    })


@login_required
@user_passes_test(is_admin)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        name = product.name
        product.delete()
        messages.success(request, f"Đã xóa sản phẩm '{name}'.")
        return redirect("product_list")

    return render(request, "inventory/confirm_delete.html", {
        "object": product,
        "title": "Xóa sản phẩm"
    })


@login_required
def order_create(request):
    product_id = request.GET.get("product")
    initial = {}

    if product_id:
        initial["product"] = get_object_or_404(Product, pk=product_id, status="active")

    form = OrderForm(request.POST or None, initial=initial)

    if form.is_valid():
        order = form.save(commit=False)
        order.user = request.user

        if order.quantity <= 0:
            messages.error(request, "Số lượng đặt hàng phải lớn hơn 0.")
            return redirect("order_create")

        if order.product.quantity < order.quantity:
            messages.error(request, f"Kho chỉ còn {order.product.quantity} sản phẩm, không đủ số lượng bạn yêu cầu.")
            return redirect("home")

        order.save()
        messages.success(request, "Tạo đơn đặt hàng thành công! Vui lòng chờ quản trị viên duyệt.")
        return redirect("my_orders")

    return render(request, "inventory/form.html", {
        "form": form,
        "title": "Tạo đơn đặt hàng"
    })


@login_required
def my_orders(request):
    orders = Order.objects.filter(user=request.user).select_related("product").order_by("-created_at")
    return render(request, "inventory/my_orders.html", {
        "orders": orders
    })


@login_required
@user_passes_test(is_admin)
def order_list(request):
    status_filter = request.GET.get("status", "")
    orders = Order.objects.select_related("user", "product").order_by("-created_at")
    if status_filter:
        orders = orders.filter(status=status_filter)

    return render(request, "inventory/order_list.html", {
        "orders": orders,
        "status_filter": status_filter,
    })


@login_required
@user_passes_test(is_admin)
def order_approve(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if order.status != "pending":
        messages.warning(request, "Đơn hàng này đã được xử lý trước đó.")
        return redirect("order_list")

    if order.product.quantity < order.quantity:
        messages.error(request, "Tồn kho không đủ số lượng để duyệt đơn hàng này.")
        return redirect("order_list")

    product = order.product
    product.quantity -= order.quantity
    product.save()

    order.status = "approved"
    order.save()

    StockHistory.objects.create(
        product=product,
        action="order",
        quantity=order.quantity,
        note=f"Xuất kho theo đơn hàng #{order.id} ({order.user.username})"
    )

    messages.success(request, f"Đã duyệt đơn hàng #{order.id} và tự động trừ tồn kho.")
    return redirect("order_list")


@login_required
@user_passes_test(is_admin)
def order_reject(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if order.status != "pending":
        messages.warning(request, "Đơn hàng này đã được xử lý trước đó.")
        return redirect("order_list")

    order.status = "rejected"
    order.save()

    messages.info(request, f"Đã từ chối đơn hàng #{order.id}.")
    return redirect("order_list")
