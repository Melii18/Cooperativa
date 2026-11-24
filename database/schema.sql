CREATE DATABASE IF NOT EXISTS cooperativa
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cooperativa;

-- USUARIOS: quienes inician sesion en el sistema
CREATE TABLE IF NOT EXISTS usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre_usuario VARCHAR(50) NOT NULL UNIQUE,
  nombre_completo VARCHAR(100) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  rol ENUM('administrador','tesorero','consulta') NOT NULL DEFAULT 'consulta',
  activo TINYINT(1) NOT NULL DEFAULT 1,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- SOCIOS: miembros de la cooperativa (baja logica con el campo estado)
CREATE TABLE IF NOT EXISTS socios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(160) NOT NULL,
  telefono VARCHAR(20) NOT NULL,
  cedula VARCHAR(20) NULL UNIQUE,
  fecha_ingreso DATE NOT NULL,
  estado ENUM('activo','inactivo') NOT NULL DEFAULT 'activo',
  UNIQUE KEY uq_socio_nombre_telefono (nombre, telefono)
);

-- CONFIGURACION: valores que el administrador puede cambiar
CREATE TABLE IF NOT EXISTS configuracion (
  clave VARCHAR(50) PRIMARY KEY,
  valor VARCHAR(100) NOT NULL,
  descripcion VARCHAR(150)
);

INSERT IGNORE INTO configuracion (clave, valor, descripcion) VALUES
  ('aporte_minimo', '20000', 'Aporte minimo mensual por socio en guaranies'),
  ('interes_porcentaje', '10.00', 'Interes en porcentaje que se suma a cada cuota mensual del prestamo'),
  ('monto_maximo_prestamo', '10000000', 'Monto maximo por prestamo en guaranies'),
  ('monto_maximo_prestamo', '10000000', 'Monto maximo por prestamo en guaranies'),
  ('max_cuotas', '24', 'Cantidad maxima de cuotas por prestamo');

-- APORTES: un aporte por socio y por mes
CREATE TABLE IF NOT EXISTS aportes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  socio_id INT NOT NULL,
  anio SMALLINT NOT NULL,
  mes TINYINT NOT NULL,
  monto DECIMAL(12,0) NOT NULL,
  fecha_pago DATE NOT NULL,
  estado ENUM('vigente','anulado') NOT NULL DEFAULT 'vigente',
  registrado_por INT NOT NULL,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  clave_vigente VARCHAR(20) GENERATED ALWAYS AS
    (IF(estado = 'vigente', CONCAT_WS('-', socio_id, anio, mes), NULL)) STORED,
  UNIQUE KEY uq_aporte_vigente (clave_vigente),
  CONSTRAINT chk_aporte_monto CHECK (monto > 0),
  CONSTRAINT chk_aporte_mes CHECK (mes BETWEEN 1 AND 12),
  FOREIGN KEY (socio_id) REFERENCES socios(id),
  FOREIGN KEY (registrado_por) REFERENCES usuarios(id)
);

-- PRESTAMOS: un solo prestamo activo por socio
CREATE TABLE IF NOT EXISTS prestamos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  socio_id INT NOT NULL,
  monto_prestado DECIMAL(12,0) NOT NULL,
  interes_porcentaje DECIMAL(5,2) NOT NULL,
  cantidad_cuotas TINYINT NOT NULL,
  total_a_pagar DECIMAL(12,0) NOT NULL,
  saldo_pendiente DECIMAL(12,0) NOT NULL,
  fecha_desembolso DATE NOT NULL,
  estado ENUM('activo','cancelado','anulado') NOT NULL DEFAULT 'activo',
  registrado_por INT NOT NULL,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  socio_activo INT GENERATED ALWAYS AS
    (IF(estado = 'activo', socio_id, NULL)) STORED,
  UNIQUE KEY uq_un_prestamo_activo (socio_activo),
  CONSTRAINT chk_prestamo_monto CHECK (monto_prestado > 0),
  CONSTRAINT chk_prestamo_cuotas CHECK (cantidad_cuotas > 0),
  CONSTRAINT chk_prestamo_saldo CHECK (saldo_pendiente >= 0),
  FOREIGN KEY (socio_id) REFERENCES socios(id),
  FOREIGN KEY (registrado_por) REFERENCES usuarios(id)
);

-- CUOTAS_PRESTAMO: el plan de pagos de cada prestamo
CREATE TABLE IF NOT EXISTS cuotas_prestamo (
  id INT AUTO_INCREMENT PRIMARY KEY,
  prestamo_id INT NOT NULL,
  numero_cuota TINYINT NOT NULL,
  fecha_vencimiento DATE NOT NULL,
  monto_cuota DECIMAL(12,0) NOT NULL,
  monto_pagado DECIMAL(12,0) NOT NULL DEFAULT 0,
  estado ENUM('pendiente','pagada') NOT NULL DEFAULT 'pendiente',
  UNIQUE KEY uq_cuota (prestamo_id, numero_cuota),
  CONSTRAINT chk_cuota_pagado CHECK (monto_pagado >= 0 AND monto_pagado <= monto_cuota),
  FOREIGN KEY (prestamo_id) REFERENCES prestamos(id)
);

-- PAGOS: cada pago aplicado a una cuota (un recibo puede cubrir varias cuotas)
CREATE TABLE IF NOT EXISTS pagos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cuota_id INT NOT NULL,
  monto DECIMAL(12,0) NOT NULL,
  fecha_pago DATE NOT NULL,
  nro_recibo VARCHAR(30) NOT NULL,
  estado ENUM('vigente','anulado') NOT NULL DEFAULT 'vigente',
  registrado_por INT NOT NULL,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  clave_vigente VARCHAR(60) GENERATED ALWAYS AS
    (IF(estado = 'vigente', CONCAT_WS('-', nro_recibo, cuota_id), NULL)) STORED,
  UNIQUE KEY uq_pago_vigente (clave_vigente),
  CONSTRAINT chk_pago_monto CHECK (monto > 0),
  FOREIGN KEY (cuota_id) REFERENCES cuotas_prestamo(id),
  FOREIGN KEY (registrado_por) REFERENCES usuarios(id)
);

-- HISTORIAL: auditoria de todas las acciones
CREATE TABLE IF NOT EXISTS historial (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT,
  accion VARCHAR(40) NOT NULL,
  tabla_afectada VARCHAR(40) NOT NULL,
  registro_id INT,
  detalle TEXT,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);