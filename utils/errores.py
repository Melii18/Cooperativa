class ErrorDeNegocio(Exception):
    """Error que se le muestra al usuario tal cual."""


class ErrorAutenticacion(ErrorDeNegocio):
    pass


class ErrorValidacion(ErrorDeNegocio):
    pass


class ErrorPermiso(ErrorDeNegocio):
    pass