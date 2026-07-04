from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()

# Hash factice, calculé une seule fois au chargement du module. Ne correspond
# à aucun mot de passe réel : sert uniquement à faire porter le coût argon2
# d'une vérification même quand aucun utilisateur ne correspond, afin de ne
# pas exposer un oracle de timing sur l'existence d'un compte (cf. AUTH-09).
DUMMY_PASSWORD_HASH = _ph.hash("docflow-dummy-password-hash-for-timing-safety")


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False
