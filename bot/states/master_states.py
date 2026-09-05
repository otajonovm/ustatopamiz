from aiogram.fsm.state import State, StatesGroup


class MasterRegistration(StatesGroup):
    category = State()
    region = State()
    experience = State()
    portfolio = State()


class SubscriptionPaymentState(StatesGroup):
    receipt = State()
