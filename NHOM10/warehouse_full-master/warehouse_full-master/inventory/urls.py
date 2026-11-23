from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # Sản phẩm (hỗ trợ cả tên product_update và product_edit)
    path("products/", views.product_list, name="product_list"),
    path("products/create/", views.product_create, name="product_create"),
    path("products/add/", views.product_create, name="product_add"),
    path("products/<int:pk>/update/", views.product_edit, name="product_update"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),

    # Nhập kho & lịch sử kho
    path("stock/import/", views.stock_import, name="stock_import"),
    path("stock/history/", views.stock_history_list, name="stock_history_list"),

    # Đơn đặt hàng & phiếu xuất kho
    path("orders/create/", views.order_create, name="order_create"),
    path("orders/my/", views.my_orders, name="my_orders"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:pk>/approve/", views.order_approve, name="order_approve"),
    path("orders/<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("orders/<int:pk>/invoice/", views.order_invoice, name="order_invoice"),

    # Xác thực mở rộng
    path("accounts/register/", views.register_view, name="register"),
    path("accounts/otp-login/", views.phone_otp_login, name="phone_otp_login"),
    path("accounts/google-entry/", views.google_login_entry, name="google_login_entry"),
    path("accounts/password-reset/", views.password_reset_view, name="password_reset_custom"),
]
