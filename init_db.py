#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Initialize the database with all tables"""

from app import create_app, db

app = create_app()

with app.app_context():
    # Drop all tables
    print("Dropping existing tables...")
    db.drop_all()
    
    # Create all tables
    print("Creating new tables...")
    db.create_all()
    
    print("✓ Database initialized successfully!")
    print("✓ All tables created with new columns")
