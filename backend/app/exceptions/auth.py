class AuthenticationException(Exception):
    """
    Base authentication exception.
    """


class InvalidCredentialsException(AuthenticationException):
    """
    Raised when invalid credentials are supplied.
    """


class InvalidCurrentPasswordException(AuthenticationException):
    """
    Raised when the current password supplied for a password change
    is incorrect.
    """


class EmailAlreadyExistsException(AuthenticationException):
    """
    Raised when attempting to register an existing email.
    """


class PhoneAlreadyExistsException(AuthenticationException):
    """
    Raised when attempting to register an existing phone number.
    """