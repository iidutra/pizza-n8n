def build_foto_url(foto_field, request=None) -> str | None:
    if not foto_field:
        return None
    url = foto_field.url
    if request:
        return request.build_absolute_uri(url)
    return url
