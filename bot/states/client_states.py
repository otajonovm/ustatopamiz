from aiogram.fsm.state import State, StatesGroup


class OrderCreation(StatesGroup):
    category = State()
    region = State()
    description = State()


class RatingState(StatesGroup):
    waiting = State()
