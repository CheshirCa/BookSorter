@echo off
setlocal enabledelayedexpansion

:: Папка для исходных файлов
set SRC=books_src
if not exist %SRC% mkdir %SRC%

:: Очистка старых файлов
del /q %SRC%\* >nul 2>&1

echo Генерация 100 тестовых файлов...

:: Windows / Office
echo. > %SRC%\Windows_Server2022.iso
echo. > %SRC%\Windows10_setup.zip
echo. > %SRC%\Office365_manual.pdf
echo. > %SRC%\Windows_PowerShell_guide.pdf

:: Programming
echo. > %SRC%\Python.for.kids.epub
echo. > %SRC%\Advanced_Python.pdf
echo. > %SRC%\PHP_MySQL_guide.pdf
echo. > %SRC%\Cplusplus.reference.rar
echo. > %SRC%\C++_primer.pdf
echo. > %SRC%\Learn_Java.epub
echo. > %SRC%\Rust_book.pdf
echo. > %SRC%\JavaScript-Basics.pdf
echo. > %SRC%\GoLang_101.pdf

:: Science
echo. > %SRC%\Physics_basics.djvu
echo. > %SRC%\Quantum_mechanics.pdf
echo. > %SRC%\Math_for_engineers.pdf
echo. > %SRC%\Biology.intro.pdf
echo. > %SRC%\Organic_Химия.pdf
echo. > %SRC%\Astronomy_Stars.epub
echo. > %SRC%\Chemistry-Lab.pdf
echo. > %SRC%\Biology_детям.pdf

:: Kids
echo. > %SRC%\Fairy_tales_for_kids.pdf
echo. > %SRC%\Математика_детям.pdf
echo. > %SRC%\Fun_with_science.epub
echo. > %SRC%\Истории_для_детей.pdf
echo. > %SRC%\Kids_Programming.pdf

:: Miscellaneous (до 100 файлов)
for /l %%i in (1,1,70) do (
  set /a r=%RANDOM% %% 6
  if !r! EQU 0 (set ext=pdf)
  if !r! EQU 1 (set ext=epub)
  if !r! EQU 2 (set ext=rar)
  if !r! EQU 3 (set ext=zip)
  if !r! EQU 4 (set ext=djvu)
  if !r! EQU 5 (set ext=iso)
  
  set /a s=%RANDOM% %% 5
  if !s! EQU 0 (set prefix=Book)
  if !s! EQU 1 (set prefix=Novel)
  if !s! EQU 2 (set prefix=Story)
  if !s! EQU 3 (set prefix=Guide)
  if !s! EQU 4 (set prefix=Manual)

  echo. > %SRC%\!prefix!_%%i.!ext!
)

echo Создание файлов завершено.
dir /b %SRC% | find /c /v ""
pause
