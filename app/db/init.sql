CREATE TABLE IF NOT EXISTS items (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL
);

INSERT INTO items (id, name, price)
SELECT i, 'item-' || i, round((random() * 100)::numeric, 2)
FROM generate_series(1, 1000) AS i
ON CONFLICT (id) DO NOTHING;
