from re import S

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