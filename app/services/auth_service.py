"""Reglas de negocio de la sesión: registrar médicos, iniciar sesión y actualizar el propio perfil.
No conoce HTTP: los errores del dominio llegan al router, que los traduce a códigos de estado."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.models.medico import Medico
from app.repositories import medico_repo
from app.schemas.auth import CambioPassword, LoginEntrada, MedicoActualizar, RegistroEntrada


class UsuarioYaExiste(Exception):
    """Ya hay un médico con ese nombre de usuario."""


class CredencialesInvalidas(Exception):
    """Usuario o contraseña incorrectos. No distingue cuál, a propósito."""


def registrar(db: Session, datos: RegistroEntrada) -> Medico:
    if medico_repo.obtener_por_usuario(db, datos.nombre_de_usuario):
        raise UsuarioYaExiste(datos.nombre_de_usuario)

    medico = Medico(
        nombre=datos.nombre,
        apellidos=datos.apellidos,
        ciudad=datos.ciudad,
        efirma=datos.efirma,
        nombre_de_usuario=datos.nombre_de_usuario,
        password=security.hashear_password(datos.password),
    )
    try:
        medico_repo.agregar(db, medico)
        db.commit()
    except IntegrityError:
        # Dos registros simultáneos pasaron la comprobación de arriba: la restricción UNIQUE decide
        db.rollback()
        raise UsuarioYaExiste(datos.nombre_de_usuario)
    return medico


def iniciar_sesion(db: Session, datos: LoginEntrada) -> tuple[str, int]:
    """Devuelve (token, segundos_de_vigencia) o lanza CredencialesInvalidas."""
    medico = medico_repo.obtener_por_usuario(db, datos.nombre_de_usuario.lower())
    if not security.verificar_password(datos.password, medico.password if medico else None):
        raise CredencialesInvalidas()

    # Si los parámetros de argon2 se endurecen con el tiempo, el hash se actualiza al iniciar sesión
    if security.necesita_rehash(medico.password):
        medico.password = security.hashear_password(datos.password)
        db.commit()
    return security.crear_token(medico.id)


def actualizar_perfil(db: Session, medico: Medico, datos: MedicoActualizar) -> Medico:
    """Actualiza los datos del médico de la sesión (el router solo le pasa a quien tiene sesión)."""
    cambios = datos.model_dump(exclude_unset=True)

    nuevo_usuario = cambios.get("nombre_de_usuario")
    if nuevo_usuario and nuevo_usuario != medico.nombre_de_usuario and medico_repo.obtener_por_usuario(db, nuevo_usuario):
        raise UsuarioYaExiste(nuevo_usuario)

    for campo, valor in cambios.items():
        setattr(medico, campo, valor)
    try:
        db.commit()
    except IntegrityError:  # dos cambios simultáneos al mismo nombre: decide la restricción UNIQUE
        db.rollback()
        raise UsuarioYaExiste(nuevo_usuario)
    return medico


def cambiar_password(db: Session, medico: Medico, datos: CambioPassword) -> None:
    """Exige la contraseña actual: una sesión abierta o robada no basta para adueñarse de la cuenta."""
    if not security.verificar_password(datos.password_actual, medico.password):
        raise CredencialesInvalidas()
    medico.password = security.hashear_password(datos.password_nueva)
    db.commit()
