CREATE TABLE users (
	id VARCHAR(36) NOT NULL,
	email VARCHAR(254) NOT NULL,
	password_hash TEXT NOT NULL,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (email)
);
CREATE TABLE employees (
	id VARCHAR(36) NOT NULL,
	code VARCHAR(80) NOT NULL,
	name VARCHAR(160) NOT NULL,
	active BOOLEAN NOT NULL,
	embeddings JSON NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (code)
);
CREATE TABLE kiosks (
	id VARCHAR(36) NOT NULL,
	name VARCHAR(160) NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (token_hash)
);
CREATE TABLE webhook_subscriptions (
	id VARCHAR(36) NOT NULL,
	name VARCHAR(160) NOT NULL,
	url TEXT NOT NULL,
	secret TEXT NOT NULL,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);
CREATE TABLE admin_sessions (
	token_hash VARCHAR(64) NOT NULL,
	user_id VARCHAR(36) NOT NULL,
	expires_at FLOAT NOT NULL,
	PRIMARY KEY (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE attendance_logs (
	id VARCHAR(36) NOT NULL,
	event_id VARCHAR(36) NOT NULL,
	kiosk_id VARCHAR(36) NOT NULL,
	employee_id VARCHAR(36) NOT NULL,
	captured_at FLOAT NOT NULL,
	received_at FLOAT NOT NULL,
	confidence FLOAT NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (kiosk_id, event_id),
	FOREIGN KEY(kiosk_id) REFERENCES kiosks (id),
	FOREIGN KEY(employee_id) REFERENCES employees (id)
);
CREATE TABLE webhook_deliveries (
	id VARCHAR(36) NOT NULL,
	subscription_id VARCHAR(36) NOT NULL,
	payload JSON NOT NULL,
	state VARCHAR(20) NOT NULL,
	attempts INTEGER NOT NULL,
	next_attempt_at FLOAT NOT NULL,
	last_status INTEGER,
	last_error TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(subscription_id) REFERENCES webhook_subscriptions (id)
);
CREATE INDEX ix_webhook_deliveries_next_attempt_at ON webhook_deliveries (next_attempt_at);
