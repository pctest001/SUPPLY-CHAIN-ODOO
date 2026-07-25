# 学习：类定义、init、实例方法、类方法 done
# 学习：继承、方法重写  done 
# 学习：属性访问（@property）
# 学习：特殊方法（str, repr）
# 练习4：定义 OdooModel 基类和 StockQuant 子类
# 学习：HTTP 协议基础（GET/POST/状态码/Header/Body）
# 学习：requests 库（get, post, headers, params, json, timeout）
# 学习：响应处理（status_code, json(), text）
# 学习：会话管理（Session）
# 实战：用 requests 调用 httpbin.org/get
# 实战：用 requests 调用 httpbin.org/post 发送 JSON body
# 实战：处理超时和异常

# 学习：类定义、init、实例方法、类方法



class Student (object):
    count = 0
    name = 'Student'
    def __init__(self, name, score):
        self.__name = name
        self.__score = score
        self._score1 = score
        Student.count+=1
    
    def play (self):
        print (shuyi.__name+" is playing")
    def get_grade(self):
        if self.__score >= 90:
            return 'A'
        elif self.__score >= 60:
            return 'B'
        else:
            return 'C'
    def print_score(self):
        print('%s: %s' % (self.__name, self.__score))

    def get_name(self):
        return self.__name

    def get_score(self):
        return self.__score
    def set_score(self, score):
        if 0 <= score <= 100:
            self.__score = score
        else:
            raise ValueError('bad score')
    @property
    def score1(self):
        return self._score1

    @score1.setter
    def score1(self, value):
        if not isinstance(value, int):
            raise ValueError('score1 must be an integer!')
        if value < 0 or value > 100:
            raise ValueError('score must between 0 ~ 100!')
        self._score1 = value

shuyi: Student =Student('shuyi', 99)
shuyi.play()
print (shuyi.get_grade())
shuyi.print_score()
Student.name='Student1'
print(Student.name)

# 学习：继承、方法重写
class Animal(object):
    def run(self):
        print('Animal is running...')

class Dog(Animal):
    def run(self):
        print('Dog is running...')  
    def eat(self):
        print('Dog is eating shi')  
class Cat(Animal):
    pass

cat =Cat()
cat.run()
dog =Dog()
dog.run()
dog.eat()