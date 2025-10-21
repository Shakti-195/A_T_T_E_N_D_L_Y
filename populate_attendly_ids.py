from attendly import create_app
from attendly.extensions import db
from attendly.models import User

app = create_app()

with app.app_context():
    users = User.query.filter_by(attendly_id=None).all()
    for user in users:
        user.attendly_id = f"ATD{user.id:06d}"
    db.session.commit()
    print(f"✅ Updated {len(users)} users with attendly_id")