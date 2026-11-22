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
