CREATE TABLE bill (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    owner VARCHAR(100) NOT NULL,
    due_date DATE NOT NULL,
    amount NUMERIC(10,2) NOT NULL
);

CREATE TABLE income (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    frequency VARCHAR(20) NOT NULL,
    next_pay DATE NOT NULL
);

