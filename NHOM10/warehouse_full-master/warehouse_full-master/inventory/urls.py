from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/export-csv/", views.export_inventory_csv, name="export_inventory_csv"),

    path("products/", views.product_list, name="product_list"),
    path("products/create/", views.product_create, name="product_create"),
    path("products/<int:pk>/update/", views.product_update, name="product_update"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),

    path("stock/import/", views.stock_import, name="stock_import"),
    path("stock/history/", views.stock_history_list, name="stock_history_list"),
    path("stock/history/export-csv/", views.export_history_csv, name="export_history_csv"),

    path("orders/create/", views.order_create, name="order_create"),
    path("orders/my/", views.my_orders, name="my_orders"),
    path("orders/manage/", views.order_list, name="order_list"),
    path("orders/<int:pk>/approve/", views.order_approve, name="order_approve"),
    path("orders/<int:pk>/reject/", views.order_reject, name="order_reject"),
    path("orders/<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("orders/<int:pk>/invoice/", views.order_invoice, name="order_invoice"),
]
