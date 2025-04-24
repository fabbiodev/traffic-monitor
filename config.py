import os
class Config:
    LANGUAGES = ['en', 'ru']
    DB_PATH = os.path.join(os.path.dirname(__file__), 'stats.db')
