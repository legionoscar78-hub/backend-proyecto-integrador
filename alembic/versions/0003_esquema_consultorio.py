"""esquema consultorio

Rediseña la base de datos para que tenga la estructura de docs/ScriptDb.sql:
medicos, pacientes, citas, consultas, enfermedades, sintomas y enfermedadesdetalle.
Los nombres de tablas, columnas, restricciones e índices son los del script.

Desaparecen: medico, paciente, consulta, consulta_sintoma, prediccion y prediccion_detalle, y las
columnas extra del catálogo (descripcion_es, cie10_codigo, nombre_es). El catálogo se recarga con
scripts/seed_catalogo.py. Los datos de medico/paciente/consulta no se migran: si ya hay filas, la
migración se detiene en vez de borrarlas.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas del diseño anterior que guardan datos del usuario (el catálogo se puede recargar)
TABLAS_CON_DATOS = ("prediccion_detalle", "prediccion", "consulta_sintoma", "consulta", "paciente", "medico")


def _verificar_que_no_hay_datos() -> None:
    if context.is_offline_mode():
        return
    conexion = op.get_bind()
    con_filas = {
        t: n for t in TABLAS_CON_DATOS
        if (n := conexion.execute(sa.text(f"select count(*) from {t}")).scalar_one())
    }
    if con_filas:
        detalle = ", ".join(f"{t} ({n} filas)" for t, n in con_filas.items())
        raise RuntimeError(
            f"No se puede migrar: hay datos en {detalle}. Esta migración no los convierte al "
            "esquema nuevo. Haz un respaldo y vacía esas tablas (o migra los datos a mano) y "
            "vuelve a ejecutar alembic upgrade."
        )


def upgrade() -> None:
    _verificar_que_no_hay_datos()

    # --- Diseño anterior (en orden inverso por dependencias) ---
    op.drop_table('prediccion_detalle')
    op.drop_table('prediccion')
    op.drop_table('consulta_sintoma')
    op.drop_table('consulta')
    op.drop_table('paciente')
    op.drop_table('medico')
    op.drop_table('enfermedadesdetalle')
    op.drop_table('sintomas')
    op.drop_table('enfermedades')

    # --- Diseño de docs/ScriptDb.sql ---
    op.create_table(
        'medicos',
        sa.Column('medicoid', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('apellidos', sa.String(length=150), nullable=False),
        sa.Column('ciudad', sa.String(length=100), nullable=False),
        sa.Column('efirma', sa.Text(), nullable=False),
        sa.Column('nombredeusuario', sa.String(length=50), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('medicoid', name='pk_medicos'),
        sa.UniqueConstraint('nombredeusuario', name='uq_medicos_usuario'),
    )
    op.create_table(
        'pacientes',
        sa.Column('pacienteid', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('apellidos', sa.String(length=150), nullable=False),
        sa.Column('curp', sa.CHAR(length=18), nullable=False),
        sa.Column('fechanacimiento', sa.Date(), nullable=False),
        sa.Column('numerotelefonico', sa.String(length=15), nullable=True),
        sa.Column('sexo', sa.CHAR(length=1), nullable=False),
        sa.Column('tipodesangre', sa.String(length=3), nullable=True),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('pacienteid', name='pk_pacientes'),
        sa.UniqueConstraint('curp', name='uq_pacientes_curp'),
        sa.CheckConstraint("sexo IN ('H', 'M')", name='ck_pacientes_sexo'),
        sa.CheckConstraint(
            "tipodesangre IS NULL OR tipodesangre IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')",
            name='ck_pacientes_tiposangre',
        ),
        sa.CheckConstraint('fechanacimiento <= CURRENT_DATE', name='ck_pacientes_fechanac'),
    )
    op.create_table(
        'enfermedades',
        sa.Column('enfermedadid', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('nombreenfermedad', sa.String(length=150), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('enfermedadid', name='pk_enfermedades'),
        sa.UniqueConstraint('nombreenfermedad', name='uq_enfermedades_nombre'),
    )
    op.create_table(
        'sintomas',
        sa.Column('sintomaid', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('nombresintoma', sa.String(length=150), nullable=False),
        sa.PrimaryKeyConstraint('sintomaid', name='pk_sintomas'),
        sa.UniqueConstraint('nombresintoma', name='uq_sintomas_nombre'),
    )
    op.create_table(
        'citas',
        sa.Column('citaid', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('medicoid', sa.Integer(), nullable=False),
        sa.Column('pacienteid', sa.Integer(), nullable=False),
        sa.Column('fechacita', sa.Date(), nullable=False),
        sa.Column('horacita', sa.Time(), nullable=False),
        sa.PrimaryKeyConstraint('citaid', name='pk_citas'),
        sa.ForeignKeyConstraint(['medicoid'], ['medicos.medicoid'], name='fk_citas_medico',
                                onupdate='CASCADE', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['pacienteid'], ['pacientes.pacienteid'], name='fk_citas_paciente',
                                onupdate='CASCADE', ondelete='RESTRICT'),
        sa.UniqueConstraint('medicoid', 'fechacita', 'horacita', name='uq_citas_medico_horario'),
    )
    op.create_table(
        'consultas',
        sa.Column('consultaid', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('medicoid', sa.Integer(), nullable=False),
        sa.Column('pacienteid', sa.Integer(), nullable=False),
        sa.Column('enfermedadid', sa.Integer(), nullable=False),
        sa.Column('edad', sa.SmallInteger(), nullable=False),
        sa.Column('peso', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('altura', sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column('fechaconsulta', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('llave', sa.String(length=100), nullable=False),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('consultaid', name='pk_consultas'),
        sa.UniqueConstraint('llave', name='uq_consultas_llave'),
        sa.ForeignKeyConstraint(['medicoid'], ['medicos.medicoid'], name='fk_consultas_medico',
                                onupdate='CASCADE', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['pacienteid'], ['pacientes.pacienteid'], name='fk_consultas_paciente',
                                onupdate='CASCADE', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['enfermedadid'], ['enfermedades.enfermedadid'], name='fk_consultas_enfermedad',
                                onupdate='CASCADE', ondelete='RESTRICT'),
        sa.CheckConstraint('edad BETWEEN 0 AND 150', name='ck_consultas_edad'),
        sa.CheckConstraint('peso IS NULL OR peso > 0', name='ck_consultas_peso'),
        sa.CheckConstraint('altura IS NULL OR altura > 0', name='ck_consultas_altura'),
    )
    op.create_table(
        'enfermedadesdetalle',
        sa.Column('enfermedaddetalleid', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('enfermedadid', sa.Integer(), nullable=False),
        sa.Column('sintomaid', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('enfermedaddetalleid', name='pk_enfermedadesdetalle'),
        sa.ForeignKeyConstraint(['enfermedadid'], ['enfermedades.enfermedadid'], name='fk_enfdet_enfermedad',
                                onupdate='CASCADE', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sintomaid'], ['sintomas.sintomaid'], name='fk_enfdet_sintoma',
                                onupdate='CASCADE', ondelete='CASCADE'),
        sa.UniqueConstraint('enfermedadid', 'sintomaid', name='uq_enfdet_enfermedad_sintoma'),
    )

    op.create_index('ix_citas_paciente', 'citas', ['pacienteid'])
    op.create_index('ix_citas_fecha', 'citas', ['fechacita'])
    op.create_index('ix_consultas_medico', 'consultas', ['medicoid'])
    op.create_index('ix_consultas_paciente', 'consultas', ['pacienteid'])
    op.create_index('ix_consultas_enfermedad', 'consultas', ['enfermedadid'])
    op.create_index('ix_enfdet_sintoma', 'enfermedadesdetalle', ['sintomaid'])


def downgrade() -> None:
    """Vuelve al diseño anterior (revisión 0002). Las tablas quedan vacías: no se conservan datos."""
    if not context.is_offline_mode():
        conexion = op.get_bind()
        con_filas = {
            t: n for t in ("citas", "consultas", "pacientes", "medicos")
            if (n := conexion.execute(sa.text(f"select count(*) from {t}")).scalar_one())
        }
        if con_filas:
            detalle = ", ".join(f"{t} ({n} filas)" for t, n in con_filas.items())
            raise RuntimeError(f"No se puede volver atrás: hay datos en {detalle} y el diseño anterior no los admite.")

    op.drop_table('enfermedadesdetalle')   # sus índices y restricciones se borran con la tabla
    op.drop_table('consultas')
    op.drop_table('citas')
    op.drop_table('sintomas')
    op.drop_table('enfermedades')
    op.drop_table('pacientes')
    op.drop_table('medicos')

    op.create_table(
        'enfermedades',
        sa.Column('enfermedadid', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('descripcion', sa.String(length=500), nullable=False),
        sa.Column('descripcion_es', sa.String(length=500), nullable=True),
        sa.Column('cie10_codigo', sa.String(length=3), nullable=True),
        sa.PrimaryKeyConstraint('enfermedadid', name=op.f('pk_enfermedades')),
    )
    op.create_table(
        'medico',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('apellidos', sa.String(length=100), nullable=False),
        sa.Column('especialidad', sa.String(length=100), nullable=False),
        sa.Column('direccion_consultorio', sa.String(length=200), nullable=False),
        sa.Column('correo', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('fecha_registro', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_medico')),
        sa.UniqueConstraint('correo', name=op.f('uq_medico_correo')),
    )
    op.create_table(
        'sintomas',
        sa.Column('sintomaid', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('nombresintoma', sa.String(length=100), nullable=False),
        sa.Column('nombre_es', sa.String(length=150), nullable=True),
        sa.PrimaryKeyConstraint('sintomaid', name=op.f('pk_sintomas')),
        sa.UniqueConstraint('nombresintoma', name=op.f('uq_sintomas_nombresintoma')),
    )
    op.create_table(
        'enfermedadesdetalle',
        sa.Column('detalleid', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('enfermedadid', sa.Integer(), nullable=False),
        sa.Column('sintomaid', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['enfermedadid'], ['enfermedades.enfermedadid'], name='fk_detalle_enfermedad', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['sintomaid'], ['sintomas.sintomaid'], name='fk_detalle_sintoma', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('detalleid', name=op.f('pk_enfermedadesdetalle')),
        sa.UniqueConstraint('enfermedadid', 'sintomaid', name='uq_enfermedad_sintoma'),
    )
    op.create_index('ix_detalle_sintoma', 'enfermedadesdetalle', ['sintomaid'], unique=False)
    op.create_table(
        'paciente',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('medico_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('apellidos', sa.String(length=100), nullable=False),
        sa.Column('fecha_nacimiento', sa.Date(), nullable=False),
        sa.Column('telefono', sa.String(length=10), nullable=False),
        sa.Column('fecha_registro', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], name=op.f('fk_paciente_medico_id_medico'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_paciente')),
    )
    op.create_index(op.f('ix_paciente_medico_id'), 'paciente', ['medico_id'], unique=False)
    op.create_table(
        'consulta',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('paciente_id', sa.Integer(), nullable=False),
        sa.Column('medico_id', sa.Integer(), nullable=False),
        sa.Column('paciente_peso', sa.Double(), nullable=False),
        sa.Column('paciente_altura', sa.Double(), nullable=False),
        sa.Column('paciente_edad', sa.Integer(), nullable=False),
        sa.Column('fecha_consulta', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('motivo', sa.String(length=500), nullable=False),
        sa.Column('tratamiento', sa.Text(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('diagnostico_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['diagnostico_id'], ['enfermedades.enfermedadid'], name=op.f('fk_consulta_diagnostico_id_enfermedades'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], name=op.f('fk_consulta_medico_id_medico'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['paciente_id'], ['paciente.id'], name=op.f('fk_consulta_paciente_id_paciente'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_consulta')),
    )
    op.create_index(op.f('ix_consulta_diagnostico_id'), 'consulta', ['diagnostico_id'], unique=False)
    op.create_index(op.f('ix_consulta_medico_id'), 'consulta', ['medico_id'], unique=False)
    op.create_index(op.f('ix_consulta_paciente_id'), 'consulta', ['paciente_id'], unique=False)
    op.create_table(
        'consulta_sintoma',
        sa.Column('consulta_id', sa.Integer(), nullable=False),
        sa.Column('sintoma_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['consulta_id'], ['consulta.id'], name=op.f('fk_consulta_sintoma_consulta_id_consulta'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sintoma_id'], ['sintomas.sintomaid'], name=op.f('fk_consulta_sintoma_sintoma_id_sintomas'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('consulta_id', 'sintoma_id', name=op.f('pk_consulta_sintoma')),
    )
    op.create_table(
        'prediccion',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('consulta_id', sa.Integer(), nullable=False),
        sa.Column('modelo_version', sa.String(length=50), nullable=False),
        sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['consulta_id'], ['consulta.id'], name=op.f('fk_prediccion_consulta_id_consulta'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_prediccion')),
    )
    op.create_index(op.f('ix_prediccion_consulta_id'), 'prediccion', ['consulta_id'], unique=False)
    op.create_table(
        'prediccion_detalle',
        sa.Column('prediccion_id', sa.Integer(), nullable=False),
        sa.Column('enfermedad_id', sa.Integer(), nullable=False),
        sa.Column('probabilidad', sa.Double(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['enfermedad_id'], ['enfermedades.enfermedadid'], name=op.f('fk_prediccion_detalle_enfermedad_id_enfermedades'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['prediccion_id'], ['prediccion.id'], name=op.f('fk_prediccion_detalle_prediccion_id_prediccion'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('prediccion_id', 'enfermedad_id', name=op.f('pk_prediccion_detalle')),
    )
