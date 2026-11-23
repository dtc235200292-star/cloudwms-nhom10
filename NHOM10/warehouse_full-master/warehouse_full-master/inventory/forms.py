from django import forms
from .models import Order, Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["sku", "name", "category", "unit", "price", "stock", "description", "image"]
        widgets = {
            "sku": forms.TextInput(attrs={"class": "form-control", "placeholder": "VD: SP001"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tên sản phẩm"}),
            "category": forms.TextInput(attrs={"class": "form-control", "placeholder": "Danh mục"}),
            "unit": forms.TextInput(attrs={"class": "form-control", "placeholder": "Cái, Hộp, Thùng..."}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "stock": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }


class StockImportForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        label="Sản phẩm nhập kho",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        label="Số lượng nhập",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1", "placeholder": "Nhập số lượng > 0"}),
    )
    batch_code = forms.CharField(
        required=False,
        max_length=50,
        label="Mã lô hàng",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "VD: LO-2026-01"}),
    )
    supplier = forms.CharField(
        required=False,
        max_length=120,
        label="Nhà cung cấp",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Tên nhà cung cấp"}),
    )
    note = forms.CharField(
        required=False,
        max_length=255,
        label="Ghi chú nhập kho",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ghi chú thêm (nếu có)"}),
    )


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["customer_name", "phone", "address", "delivery_method", "note"]
        widgets = {
            "customer_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Họ tên người nhận"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Số điện thoại liên hệ"}),
            "address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Địa chỉ giao hàng"}),
            "delivery_method": forms.Select(attrs={"class": "form-select"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Ghi chú đơn hàng"}),
        }
