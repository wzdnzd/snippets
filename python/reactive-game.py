# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-03-16

import random
import sys
import time

from PyQt5 import QtCore, QtGui, QtWidgets

flag1 = 1
Best_T = 999
t1 = time.time()
t2 = time.time()
t3 = 0


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(740, 480)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        font = QtGui.QFont()
        font.setFamily("等线 Light")
        font.setPointSize(14)

        font2 = QtGui.QFont()
        font2.setFamily("等线 Light")
        font2.setPointSize(14)

        self.items = []

        for i in range(5):
            for j in range(5):
                m = 110 + 50 * j
                n = 60 + 50 * i
                p = QtWidgets.QPushButton(self.centralwidget)
                p.setGeometry(QtCore.QRect(m, n, 50, 50))
                p.setObjectName("p_{}".format(5 * i + j + 1))
                p.setFont(font)
                self.items.append(p)

        self.pushButton = QtWidgets.QPushButton(self.centralwidget)
        self.pushButton.setGeometry(QtCore.QRect(110, 320, 251, 61))
        font = QtGui.QFont()
        font.setFamily("AcadEref")
        font.setPointSize(28)
        self.pushButton.setFont(font)
        self.pushButton.setObjectName("pushButton")
        self.textBrowser = QtWidgets.QTextBrowser(self.centralwidget)
        self.textBrowser.setGeometry(QtCore.QRect(370, 60, 300, 100))
        self.textBrowser.setObjectName("textBrowser")

        self.textBrowser2 = QtWidgets.QTextBrowser(self.centralwidget)
        self.textBrowser2.setGeometry(QtCore.QRect(370, 160, 300, 140))
        self.textBrowser2.setObjectName("textBrowser")
        self.textBrowser.setFont(font2)
        self.textBrowser2.setFont(font2)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 640, 23))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        self.pushButton.clicked.connect(self.get_num)
        # self.Button_2.clicked.connect(self.test_new)
        for item in self.items:
            item.clicked.connect(lambda _, b=item: self.user_select(btn=b))
            item.setCheckable(True)
            item.setAutoExclusive(True)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "舒尔特方格   Ver 1.0"))
        for item in self.items:
            item.setText(_translate("MainWindow", "**"))

        self.pushButton.setText(_translate("MainWindow", "开始"))

        self.textBrowser.setText(_translate("MainWindow", "\n游戏说明："))
        self.textBrowser2.setText(
            _translate("MainWindow", "点击“开始”按钮" + "\n按顺序从1点击到25" + "\n时间越短大脑反应越快")
        )

    def get_num(self):
        global flag1
        global t1, t2, Best_T
        t1 = time.time()
        list1 = []
        while len(list1) < 25:
            x = random.randint(1, 25)
            if x not in list1:
                list1.append(x)

        for i in range(25):
            item = self.items[i]
            item.setText(QtCore.QCoreApplication.translate("MainWindow", str(list1[i])))

        self.pushButton.setVisible(False)
        self.textBrowser.setText(str("宝宝，请点击数字：" + "  " + str(flag1)))
        self.textBrowser2.setText("计时开始！！！")

    def test_new(self):
        _translate = QtCore.QCoreApplication.translate
        for item in self.items:
            item.setText(_translate("MainWindow", "**"))

        self.pushButton.setVisible(True)

    def user_select(self, btn):
        global flag1
        global t2, t1, t3, Best_T

        if btn.text() == str(flag1):
            flag1 = flag1 + 1
            t2 = time.time()
            t3 = t2 - t1

        if flag1 <= 25:
            self.textBrowser.setText(str("宝宝，请点击数字：" + " " + str(flag1)))
            self.textBrowser2.setText(str("此时用时： " + "  " + str(int(t3)) + "  秒"))
        else:
            if int(t3) < int(Best_T):
                Best_T = t3
            self.textBrowser.setText(str("宝，你已完成游戏!"))
            self.textBrowser2.setText(
                str("宝，你总用时：" + " " + str(int(t3)) + " 秒" + "\n\n" + "最佳：" + str(int(Best_T)))
            )
            flag1 = 1
            _translate = QtCore.QCoreApplication.translate
            for item in self.items:
                item.setText(_translate("MainWindow", "**"))

            self.pushButton.setText(_translate("MainWindow", "重玩"))
            self.pushButton.setVisible(True)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())
