-- POSProctor 2.0 Database Schema

-- Commanders table
CREATE TABLE IF NOT EXISTS commanders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL UNIQUE,
    store_name TEXT NOT NULL,
    group_name TEXT,
    brand TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Settings table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    data_type TEXT DEFAULT 'string',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Credentials table
CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- TLOG files metadata table
CREATE TABLE IF NOT EXISTS tlog_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commander_ip TEXT NOT NULL,
    store_name TEXT NOT NULL,
    filename TEXT NOT NULL,
    period TEXT,
    file_size INTEGER,
    transaction_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (commander_ip) REFERENCES commanders(ip)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_commanders_enabled ON commanders(enabled);
CREATE INDEX IF NOT EXISTS idx_commanders_brand ON commanders(brand);
CREATE INDEX IF NOT EXISTS idx_commanders_group ON commanders(group_name);
CREATE INDEX IF NOT EXISTS idx_tlog_files_ip ON tlog_files(commander_ip);
CREATE INDEX IF NOT EXISTS idx_tlog_files_created ON tlog_files(created_at);
CREATE INDEX IF NOT EXISTS idx_credentials_default ON credentials(is_default);

-- Insert default settings
INSERT OR IGNORE INTO settings (key, value, data_type) VALUES
    ('timeout_seconds', '30', 'integer'),
    ('max_workers', '10', 'integer'),
    ('poll_interval', '300', 'integer'),
    ('xml_debug_enabled', 'false', 'boolean'),
    ('xml_debug_retention_minutes', '60', 'integer');

-- Insert default credentials (will be overridden by env vars)
INSERT OR IGNORE INTO credentials (username, password, is_default) VALUES
    ('admin', 'changeme', 1);
