from aiogram.fsm.state import State, StatesGroup

class AddTask(StatesGroup):
    waiting_for_channel = State()
    waiting_for_sub_count = State()

class TaskView(StatesGroup):
    viewing_tasks = State()