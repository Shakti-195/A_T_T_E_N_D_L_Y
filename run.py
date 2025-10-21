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
    
    # Re-create default subjects in the fresh database
    default_subjects = ['Mathematics', 'English', 'Science', 'History', 'Geography']
    for subject_name in default_subjects:
        if not Subject.query.filter_by(name=subject_name).first():
            subject = Subject(name=subject_name)
            db.session.add(subject)
    
    db.session.commit()
    click.echo('Initialized the database and created default subjects.')


# --- Main Application Runner ---
if __name__ == '__main__':
    # This block runs when the script is executed directly
    with app.app_context():
        # This is a less forceful way to ensure tables exist on startup
        # The 'init-db' command should be used for a full reset.
        db.create_all()
        
        # Create default subjects if they don't already exist on initial run
        default_subjects = ['Mathematics', 'English', 'Science', 'History', 'Geography']
        for subject_name in default_subjects:
            if not Subject.query.filter_by(name=subject_name).first():
                subject = Subject(name=subject_name)
                db.session.add(subject)
        
        # Try to commit the new subjects to the database
        try:
            db.session.commit()
        except Exception as e:
            # If there's an error, roll back the changes and log the error
            db.session.rollback()
            app.logger.error(f"Error creating default subjects: {e}")

    # Start the development server
    app.run(debug=True)

