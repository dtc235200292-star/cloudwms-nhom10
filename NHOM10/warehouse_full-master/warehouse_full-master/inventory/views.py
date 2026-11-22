import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Q, Sum, F
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
    low_stock_products = Product.objects.filter(quantity__lte=5).order_by("quantity")
    pending_orders = Order.objects.filter(status="pending").count()
    approved_orders = Order.objects.filter(status="approved").count()

    total_value = Product.objects.aggregate(
        val=Sum(F("quantity") * F("price"))
    )["val"] or 0

    categories = Category.objects.all()
    cat_labels = []
    cat_quantities = []
    for cat in categories:
        cat_labels.append(cat.name)
        qty = Product.objects.filter(category=cat).aggregate(s=Sum("quantity"))["s"] or 0
        cat_quantities.append(qty)

    recent_histories = StockHistory.objects.select_related("product").order_by("-created_at")[:10]

    return render(request, "inventory/dashboard.html", {
        "total_products": total_products,
        "total_stock": total_stock,
        "low_stock_products": low_stock_products,
        "pending_orders": pending_orders,
        "approved_orders": approved_orders,
        "total_value": total_value,
        "cat_labels": cat_labels,
        "cat_quantities": cat_quantities,
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
                    note="Khởi tạo sản phẩm mới"
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
    old_qty = product.quantity
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            updated_product = form.save()
            diff = updated_product.quantity - old_qty
            if diff != 0:
                StockHistory.objects.create(
                    product=updated_product,
                    action="import" if diff > 0 else "export",
                    quantity=abs(diff),
                    note=f"Cập nhật tồn kho từ {old_qty} thành {updated_product.quantity}"
                )
            messages.success(request, "Cập nhật sản phẩm thành công!")
            return redirect("product_list")
    else:
        form = ProductForm(instance=product)
    return render(request, "inventory/product_form.html", {"form": form, "title": "Cập nhật sản phẩm"})


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
    """Chức năng Nhập kho nhanh dành cho Admin"""
    products = Product.objects.select_related("category").all().order_by("name")

    if request.method == "POST":
        product_id = request.POST.get("product_id")
        note = request.POST.get("note", "").strip()
        try:
            qty = int(request.POST.get("quantity", 0))
        except ValueError:
            qty = 0

        if not product_id or qty <= 0:
            messages.error(request, "Vui lòng chọn sản phẩm và nhập số lượng lớn hơn 0.")
            return redirect("stock_import")

        product = get_object_or_404(Product, pk=product_id)
        product.quantity += qty
        product.save()

        StockHistory.objects.create(
            product=product,
            action="import",
            quantity=qty,
            note=note or f"Nhập kho nhanh bởi {request.user.username}"
        )

        messages.success(request, f"Đã nhập thêm {qty} sản phẩm '{product.name}' vào kho (Tồn mới: {product.quantity}).")
        return redirect("product_list")

    return render(request, "inventory/stock_import.html", {
        "products": products
    })


@login_required
def order_create(request):
    initial_data = {}
    product_param = request.GET.get("product")
    if product_param:
        initial_data["product"] = product_param

    if request.method == "POST":
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            if order.quantity > order.product.quantity:
                messages.error(request, f"Số lượng đặt ({order.quantity}) vượt quá tồn kho hiện tại ({order.product.quantity})!")
            else:
                order.user = request.user
                order.status = "pending"
                order.save()
                messages.success(request, "Đã gửi đơn đặt hàng! Vui lòng chờ Admin duyệt.")
                return redirect("my_orders")
    else:
        form = OrderForm(initial=initial_data)

    return render(request, "inventory/order_form.html", {"form": form})


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
    """Khách hàng tự hủy đơn khi đơn vẫn đang ở trạng thái Chờ duyệt"""
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
    """Trang xem & In Phiếu Xuất Kho / Hóa Đơn"""
    if request.user.is_staff:
        order = get_object_or_404(Order, pk=pk)
    else:
        order = get_object_or_404(Order, pk=pk, user=request.user)

    total_amount = order.quantity * order.product.price
    return render(request, "inventory/order_invoice.html", {
        "order": order,
        "total_amount": total_amount,
    })
