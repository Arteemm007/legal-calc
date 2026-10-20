import math
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from fractions import Fraction

app = FastAPI(title="Legal Shares Calculator")
app.mount("/static", StaticFiles(directory="static"), name="static")

class MSKRequest(BaseModel):
    price_buy: float
    msk_sum: float
    family_count: int
    area_buy: float = 0.0 # Площадь теперь опциональна, только для справки

@app.post("/api/calculate-msk")
async def calculate_msk(data: MSKRequest):
    # Расчет по закону: сумма МСК на 1 человека
    money_per_person = data.msk_sum / data.family_count
    
    # Истинная математическая доля
    min_share = money_per_person / data.price_buy
    
    # 1. Минимальная доля по МСК (в формате 1/N как в старой Excel)
    ratio = data.price_buy / money_per_person
    den_1_n = math.floor(ratio) # Округление знаменателя вниз для запаса
    if den_1_n < 1: den_1_n = 1
    
    min_share_1_n_str = f"1/{den_1_n}"
    min_share_1_n_val = 1 / den_1_n
    
    # Конвертация доли в квадратные метры
    min_share_sqm = min_share_1_n_val * data.area_buy

    # 2. Формат ЕГРН (сотые)
    num_100 = math.ceil(min_share * 100)
    share_100 = f"{num_100}/100" if num_100 <= 100 else f"{math.ceil(min_share * 1000)}/1000"
    
    # 3. Формат По площади (если площадь указана)
    if data.area_buy > 0:
        den_area = int(data.area_buy * 10)
        num_area = math.ceil(min_share * den_area)
        share_area = f"{num_area}/{den_area}"
    else:
        share_area = "-"
    
    # 4. Простая дробь
    exact_fraction = Fraction(min_share).limit_denominator(1000)
    if exact_fraction < min_share:
        exact_fraction = Fraction(exact_fraction.numerator + 1, exact_fraction.denominator)
    share_simple = f"{exact_fraction.numerator}/{exact_fraction.denominator}"
    
    return {
        "money_per_person": round(money_per_person, 2),
        "min_share": min_share_1_n_str,
        "min_share_sqm": round(min_share_sqm, 2),
        "shares": {
            "decimal_100": share_100,
            "by_area": share_area,
            "simple": share_simple
        }
    }

class OpekaRequest(BaseModel):
    old_price: float
    old_area: float
    child_num: int
    child_den: int
    new_price: float
    new_area: float
    buffer_area: float = 0.0

# Вспомогательная функция для перевода в простую дробь (с округлением вверх)
def get_simple_fraction(decimal_value: float) -> str:
    if decimal_value <= 0: return "0/1"
    if decimal_value >= 1: return "1/1"
    
    best_n = 1
    best_d = 1
    min_diff = float('inf')
    
    # Перебираем знаменатели от 1 до 99 (чтобы дробь оставалась компактной)
    for d in range(1, 100):
        # Строгое округление ВВЕРХ для каждого числителя
        n = math.ceil(decimal_value * d)
        diff = (n / d) - decimal_value
        
        # Ищем минимальную погрешность, но только в положительную сторону (n/d >= decimal_value)
        if 0 <= diff < min_diff:
            min_diff = diff
            best_n = n
            best_d = d
            
    # На случай, если дробь можно сократить (например, 2/4 -> 1/2)
    exact = Fraction(best_n, best_d)
    return f"{exact.numerator}/{exact.denominator}"

@app.post("/api/calculate-opeka")
async def calculate_opeka(data: OpekaRequest):
    # 1. Вычисляем, что было у ребенка
    child_share = data.child_num / data.child_den if data.child_den > 0 else 0
    child_old_area = (data.old_area * child_share) + data.buffer_area
    child_old_value = data.old_price * child_share

    # 2. Считаем минимально необходимые доли (десятичные)
    min_share_by_area = child_old_area / data.new_area if data.new_area > 0 else 0
    min_share_by_value = child_old_value / data.new_price if data.new_price > 0 else 0
    
    # Итоговая целевая доля (максимальная из двух)
    target_share = max(min_share_by_area, min_share_by_value)

    if target_share > 1:
        return {"status": "error", "message": "Недостаточно площади или стоимости нового объекта для выделения доли (с учетом запаса)."}

    # 3. Переводим все 3 показателя в простые дроби
    share_area_str = get_simple_fraction(min_share_by_area)
    share_value_str = get_simple_fraction(min_share_by_value)
    share_final_str = get_simple_fraction(target_share)

    # 4. Считаем реальные показатели, которые получатся при итоговой дроби
    final_val = float(Fraction(share_final_str))

    return {
        "status": "success",
        "old_stats": {
            "area": round(data.old_area * child_share, 2), 
            "value": round(child_old_value, 2)
        },
        "new_stats": {
            "area": round(data.new_area * final_val, 2),
            "value": round(data.new_price * final_val, 2)
        },
        "shares": {
            "by_area": share_area_str,
            "by_value": share_value_str,
            "final": share_final_str
        }
    }

@app.get("/")
async def serve_spa():
    return FileResponse("static/index.html")