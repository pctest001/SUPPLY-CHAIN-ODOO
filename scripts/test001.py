
import math
#函数定义、参数（位置参数 / 关键字参数 / 默认值 / *args / **kwargs）
#函数定义-参数
def are_of_circle(r):
    if not isinstance(r, (int, float)):
        raise ValueError('半径必须是数字')  
    return 3.14 * r * r

s =are_of_circle(10)
print(s)

#函数定义-无参数
def query_stock():
    pass

#函数定义-位置参数
def query_stock1(product_name, warehouse, limit=10):
    pass

def power(x):
    return x * x    
print(power(5))
#函数定义-关键字参数
def  query_metalrail(metalrail_name,metalrail_type,**other):
    print('metalrail_name:',metalrail_name,'metalrail_type:',metalrail_type,'other:',other)      

query_metalrail(metalrail_name='123',metalrail_type='123456')

query_metalrail(metalrail_name='123',metalrail_type='123456',length=10,width=20,height=30)

def person(name, age, **kw):
    if 'city' in kw:
        # 有city参数
        pass
    if 'job' in kw:
        # 有job参数
        pass
    print('name:', name, 'age:', age, 'other:', kw)

person('Jack', 24, gender='M', job='Engineer')

def person(name, age, *, city, job):
    print(name, age, city, job)

person('Jack', 24, city='Beijing', job='Engineer')
def person1(name, age, *, city, job):
    print(name, age, city, job)










def move (x,y,step,angle=0):
    x=x + step * math.cos(angle)
    y=y + step * math.sin(angle)
    return x,y
wz =move(1,1,1)
print(wz)

def quadratic(a, b, c):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not isinstance(c, (int, float)):
        raise ValueError('a,b,c必须是数字')
    if a == 0:
        # 退化成一次方程 b*x + c = 0
        if b == 0:
            return '无解' if c != 0 else '任意解'
        return 'x = %f' % (-c / b)

    delta = b * b - 4 * a * c
    if delta < 0:
        return '无解(无实根)'
    elif delta == 0:
        x = -b / (2 * a)
        return 'x1=x2=%f' % x
    else:
        sqrt_d = math.sqrt(delta)
        x1 = (-b + sqrt_d) / (2 * a)
        x2 = (-b - sqrt_d) / (2 * a)
        return 'x1=%f,x2=%f' % (x1, x2)
print('quadratic(2, 3, 1) =', quadratic(2, 3, 1))
print('quadratic(1, 3, -4) =', quadratic(1, 3, -4))
print('quadratic(1, 2, 1) =', quadratic(1, 2, 1))
print('quadratic(1, 0, 1) =', quadratic(1, 0, 1))