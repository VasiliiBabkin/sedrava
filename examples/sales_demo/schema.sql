CREATE TABLE Products (id TEXT PRIMARY KEY, title TEXT, category TEXT, price INT);
CREATE TABLE Orders (id TEXT PRIMARY KEY, product_id TEXT, amount INT, paid BOOL);
CREATE INDEX products_category ON Products(category);
CREATE INDEX orders_paid ON Orders(paid);
ALTER TABLE Orders ADD FOREIGN KEY (product_id) REFERENCES Products(id);
