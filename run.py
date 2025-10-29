from attendly import create_app, db
from attendly.models import Subject
import click

# Create an app instance from the application factory
app = create_app()

# --- CLI COMMANDS ---
@app.cli.command('init-db')
def init_db_command():
    """Clears the existing data, creates new tables, and adds default subjects."""
    db.drop_all()
    db.create_all()

    default_subjects = ['Mathematics', 'English', 'Science', 'History', 'Geography']
    for subject_name in default_subjects:
        if not Subject.query.filter_by(name=subject_name).first():
            subject = Subject(name=subject_name)
            db.session.add(subject)

    db.session.commit()
    click.echo('Initialized the database and created default subjects.')

# --- Initialize DB before serving ---
with app.app_context():
    db.create_all()
    default_subjects = ['Mathematics', 'English', 'Science', 'History', 'Geography']
    for subject_name in default_subjects:
        if not Subject.query.filter_by(name=subject_name).first():
            subject = Subject(name=subject_name)
            db.session.add(subject)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating default subjects: {e}")

# --- Only run development server locally ---
if __name__ == '__main__':
    app.run(debug=True)
