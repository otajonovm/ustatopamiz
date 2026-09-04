from aiogram.fsm.state import State, StatesGroup


class MasterRegistration(StatesGroup):
    category = State()
    region = State()
    experience = State()
