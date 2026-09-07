from aiogram.fsm.state import State, StatesGroup


class OrderCreation(StatesGroup):
    category = State()
    custom_category = State()
    village = State()
    custom_village = State()
    description = State()
