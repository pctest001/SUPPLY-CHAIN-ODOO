type(123)
print(type(123))
s = type('123')
print(s)    
s =type(123)
print(s)
print(abs)
def my_abs(x):
    if not isinstance(x, (int, float)):
        raise ValueError('bad operand type')
    if x >= 0:
        return x
    else:
        return -x   
print(my_abs)
print(type(None))

class Student(object):
    def __init__(self, name, **args):
        self.name = name
        self.score = args.get('score', None)   # 从 **args 取 score,没有则默认 None

s = Student('Bob')
s.score = 90
print(s.score)   # 90
 