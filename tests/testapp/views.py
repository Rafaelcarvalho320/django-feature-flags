from django.http import HttpRequest, HttpResponse
from django.template import Context, Template

from feature_flags import flag_required


@flag_required("new-checkout")
def guarded(request: HttpRequest) -> HttpResponse:
    return HttpResponse("the new checkout")


@flag_required("new-checkout", redirect_to="/old/")
def guarded_with_redirect(request: HttpRequest) -> HttpResponse:
    return HttpResponse("the new checkout")


def old(request: HttpRequest) -> HttpResponse:
    return HttpResponse("the old checkout")


TEMPLATE = """{% load feature_flags %}
{% flag "new-checkout" as new_checkout %}
tag:{% if new_checkout %}on{% else %}off{% endif %}
filter:{% if "new-checkout"|flag_active:request %}on{% else %}off{% endif %}"""


def rendered(request: HttpRequest) -> HttpResponse:
    return HttpResponse(Template(TEMPLATE).render(Context({"request": request})))
