-- Create Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    privilege VARCHAR(50) DEFAULT 'user'
);

-- Create Folders table
CREATE TABLE folders (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    parent_id INTEGER,
    owner_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES folders(id),
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

-- Create Files table
CREATE TABLE files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    filepath VARCHAR(255),
    mimetype VARCHAR(100),
    size INTEGER,
    is_public BOOLEAN DEFAULT FALSE,
    share_token VARCHAR(255),
    share_expiry TIMESTAMP WITH TIME ZONE,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    folder_id INTEGER,
    owner_id INTEGER,
    FOREIGN KEY (folder_id) REFERENCES folders(id),
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

-- Create indexes
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_files_filename ON files(filename);