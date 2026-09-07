from aiogram.fsm.state import State, StatesGroup


class MasterRegistration(StatesGroup):
    category = State()
    custom_category = State()
    skills = State()
    village = State()
    custom_village = State()
    experience = State()
    portfolio = State()
    confirm = State()


class SubscriptionPaymentState(StatesGroup):
    receipt = State()
