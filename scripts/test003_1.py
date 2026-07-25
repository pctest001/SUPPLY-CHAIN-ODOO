# 学习：类定义、init、实例方法、类方法
# 学习：继承、方法重写
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
# ✅ Checkpoint：能定义类和继承
# ✅ Checkpoint：能用 requests 发送 HTTP 请求并处理响应
from test003 import Student
print(Student.get_grade)
class Teacher(object):
    def __init__(self, name, score, age):
        self.name = name
        self.score = score  
        self.age = age  
    def teachStudent(self, student):
        print(self.name + " is teaching " + student.name)  
    def askStudent(self, student):
        lea = student.get_grade()
        print(self.name + " is asking " + student.name+"分数等级："+ lea)  
teacher = Teacher('zhangsan', 99, 30)
student = Student('shuyi', 99)
teacher.teachStudent(student) 
teacher.askStudent(student) 