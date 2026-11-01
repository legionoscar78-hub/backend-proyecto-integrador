-- =====================================================================
--  Script de creación de base de datos - PostgreSQL
--  Basado en el Modelo ER: Medicos, Pacientes, Citas, Consultas,
--  Enfermedades, Sintomas y EnfermedadesDetalle
--  Campos en negrita del diagrama  -> NOT NULL
--  Campos sin negrita              -> NULL permitido
-- =====================================================================

-- 1) Crear la base de datos (ejecutar conectado a la BD "postgres")
-- DROP DATABASE IF EXISTS consultorio;
CREATE DATABASE consultorio
    WITH ENCODING = 'UTF8'
    TEMPLATE = template0;

-- 2) Conectarse a la nueva base de datos (en psql)
\c consultorio

-- Limpieza opcional (en orden inverso por dependencias)
DROP TABLE IF EXISTS EnfermedadesDetalle CASCADE;
DROP TABLE IF EXISTS Consultas           CASCADE;
DROP TABLE IF EXISTS Citas               CASCADE;
DROP TABLE IF EXISTS Sintomas            CASCADE;
DROP TABLE IF EXISTS Enfermedades        CASCADE;
DROP TABLE IF EXISTS Pacientes           CASCADE;
DROP TABLE IF EXISTS Medicos             CASCADE;

-- =====================================================================
--  TABLAS CATÁLOGO / PRINCIPALES
-- =====================================================================

CREATE TABLE Medicos (
    MedicoID         INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre           VARCHAR(100) NOT NULL,
    Apellidos        VARCHAR(150) NOT NULL,
    Ciudad           VARCHAR(100) NOT NULL,
    EFirma           TEXT         NOT NULL,
    NombreDeUsuario  VARCHAR(50)  NOT NULL,
    Password         VARCHAR(255) NOT NULL,   -- guardar hash, no texto plano
    CONSTRAINT pk_medicos PRIMARY KEY (MedicoID),
    CONSTRAINT uq_medicos_usuario UNIQUE (NombreDeUsuario)
);

CREATE TABLE Pacientes (
    PacienteID        INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre            VARCHAR(100) NOT NULL,
    Apellidos         VARCHAR(150) NOT NULL,
    CURP              CHAR(18)     NOT NULL,
    FechaNacimiento   DATE         NOT NULL,
    NumeroTelefonico  VARCHAR(15),
    Sexo              CHAR(1)      NOT NULL,
    TipoDeSangre      VARCHAR(3),
    Notas             TEXT,
    CONSTRAINT pk_pacientes PRIMARY KEY (PacienteID),
    CONSTRAINT uq_pacientes_curp UNIQUE (CURP),
    CONSTRAINT ck_pacientes_sexo CHECK (Sexo IN ('H', 'M')),
    CONSTRAINT ck_pacientes_tiposangre CHECK (
        TipoDeSangre IS NULL OR
        TipoDeSangre IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')
    ),
    CONSTRAINT ck_pacientes_fechanac CHECK (FechaNacimiento <= CURRENT_DATE)
);

CREATE TABLE Enfermedades (
    EnfermedadID       INTEGER GENERATED ALWAYS AS IDENTITY,
    NombreEnfermedad   VARCHAR(150) NOT NULL,
    Descripcion        TEXT,
    CONSTRAINT pk_enfermedades PRIMARY KEY (EnfermedadID),
    CONSTRAINT uq_enfermedades_nombre UNIQUE (NombreEnfermedad)
);

CREATE TABLE Sintomas (
    SintomaID      INTEGER GENERATED ALWAYS AS IDENTITY,
    NombreSintoma  VARCHAR(150) NOT NULL,
    CONSTRAINT pk_sintomas PRIMARY KEY (SintomaID),
    CONSTRAINT uq_sintomas_nombre UNIQUE (NombreSintoma)
);

-- =====================================================================
--  TABLAS CON LLAVES FORÁNEAS
-- =====================================================================

-- Medicos (1) ---< Citas >--- (1) Pacientes
CREATE TABLE Citas (
    CitaID      INTEGER GENERATED ALWAYS AS IDENTITY,
    MedicoID    INTEGER NOT NULL,
    PacienteID  INTEGER NOT NULL,
    FechaCita   DATE    NOT NULL,
    HoraCita    TIME    NOT NULL,
    CONSTRAINT pk_citas PRIMARY KEY (CitaID),
    CONSTRAINT fk_citas_medico   FOREIGN KEY (MedicoID)
        REFERENCES Medicos (MedicoID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_citas_paciente FOREIGN KEY (PacienteID)
        REFERENCES Pacientes (PacienteID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    -- Un médico no puede tener dos citas a la misma fecha y hora
    CONSTRAINT uq_citas_medico_horario UNIQUE (MedicoID, FechaCita, HoraCita)
);

-- Medicos (1) ---< Consultas >--- (1) Pacientes
--                    Consultas >--- (1) Enfermedades
CREATE TABLE Consultas (
    ConsultaID     INTEGER GENERATED ALWAYS AS IDENTITY,
    MedicoID       INTEGER      NOT NULL,
    PacienteID     INTEGER      NOT NULL,
    EnfermedadID   INTEGER      NOT NULL,
    Edad           SMALLINT     NOT NULL,
    Peso           NUMERIC(5,2),            -- kg
    Altura         NUMERIC(4,2),            -- metros
    FechaConsulta  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Llave          VARCHAR(100) NOT NULL,
    Notas          TEXT,
    CONSTRAINT pk_consultas PRIMARY KEY (ConsultaID),
    CONSTRAINT uq_consultas_llave UNIQUE (Llave),
    CONSTRAINT fk_consultas_medico     FOREIGN KEY (MedicoID)
        REFERENCES Medicos (MedicoID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_consultas_paciente   FOREIGN KEY (PacienteID)
        REFERENCES Pacientes (PacienteID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_consultas_enfermedad FOREIGN KEY (EnfermedadID)
        REFERENCES Enfermedades (EnfermedadID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT ck_consultas_edad   CHECK (Edad BETWEEN 0 AND 150),
    CONSTRAINT ck_consultas_peso   CHECK (Peso   IS NULL OR Peso   > 0),
    CONSTRAINT ck_consultas_altura CHECK (Altura IS NULL OR Altura > 0)
);

-- Enfermedades (1) ---< EnfermedadesDetalle >--- (1) Sintomas
-- (tabla puente: relación muchos a muchos entre enfermedades y síntomas)
CREATE TABLE EnfermedadesDetalle (
    EnfermedadDetalleID  INTEGER GENERATED ALWAYS AS IDENTITY,
    EnfermedadID         INTEGER NOT NULL,
    SintomaID            INTEGER NOT NULL,
    CONSTRAINT pk_enfermedadesdetalle PRIMARY KEY (EnfermedadDetalleID),
    CONSTRAINT fk_enfdet_enfermedad FOREIGN KEY (EnfermedadID)
        REFERENCES Enfermedades (EnfermedadID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_enfdet_sintoma    FOREIGN KEY (SintomaID)
        REFERENCES Sintomas (SintomaID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    -- Evita repetir el mismo síntoma para la misma enfermedad
    CONSTRAINT uq_enfdet_enfermedad_sintoma UNIQUE (EnfermedadID, SintomaID)
);

-- =====================================================================
--  ÍNDICES SOBRE LLAVES FORÁNEAS (mejoran JOINs y búsquedas)
-- =====================================================================
CREATE INDEX ix_citas_paciente        ON Citas (PacienteID);
CREATE INDEX ix_citas_fecha           ON Citas (FechaCita);
CREATE INDEX ix_consultas_medico      ON Consultas (MedicoID);
CREATE INDEX ix_consultas_paciente    ON Consultas (PacienteID);
CREATE INDEX ix_consultas_enfermedad  ON Consultas (EnfermedadID);
CREATE INDEX ix_enfdet_sintoma        ON EnfermedadesDetalle (SintomaID);
-- (MedicoID en Citas y EnfermedadID en EnfermedadesDetalle ya quedan
--  indexados por sus restricciones UNIQUE compuestas)