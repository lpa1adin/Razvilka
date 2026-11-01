"""Реестр всех моделей: Alembic видит таблицы только тех модулей, что импортированы здесь."""

from app.core.db import Base
from app.modules.arch.models import ArchAttempt
from app.modules.assess.models import Assignment, ReferenceProject, RubricSet, Submission
from app.modules.auth.models import User, UserSession
from app.modules.courses.models import Course, CourseVersion, Enrollment, LessonProgress
from app.modules.generation.models import GenRequest
from app.modules.jobs.models import Job, WorkerHeartbeat
from app.modules.library.models import Fragment, ImportRun, Source
from app.modules.mentor.models import MentorMessage, MentorThread
from app.modules.paths.models import ProjectPath
from app.modules.practice.models import Task, TaskAttempt, TaskVersion, TaskWork
from app.modules.review.models import Review, ReviewRuleSet
from app.modules.quiz.models import Question, QuizAttempt, QuizAttemptItem, QuizTopic

__all__ = [
    "ArchAttempt", "Assignment", "Base", "Course", "CourseVersion", "Enrollment", "Fragment", "GenRequest", "ImportRun", "Job", "LessonProgress",
    "MentorMessage", "MentorThread", "ProjectPath", "ReferenceProject", "Review", "ReviewRuleSet", "RubricSet", "Submission",
    "Question", "QuizAttempt", "QuizAttemptItem", "QuizTopic", "Source", "Task", "TaskAttempt", "TaskVersion", "TaskWork", "User", "UserSession", "WorkerHeartbeat",
]
