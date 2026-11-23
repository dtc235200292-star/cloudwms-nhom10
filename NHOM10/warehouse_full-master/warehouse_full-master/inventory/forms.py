from django import forms
from .models import Order, Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["category", "supplier", "name", "sku", "quantity", "price", "image", "status"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "supplier": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tên sản phẩm"}),
            "sku": forms.TextInput(attrs={"class": "form-control", "placeholder": "VD: SP001"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
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
    note = forms.CharField(
        required=False,
        max_length=255,
        label="Ghi chú nhập kho",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Mã lô, nhà cung cấp hoặc ghi chú..."}),
    )


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["product", "quantity", "note"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": "1", "value": "1"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Địa chỉ nhận hàng, SĐT hoặc ghi chú..."}),
        }
