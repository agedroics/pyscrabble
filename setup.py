from setuptools import setup

setup(
    name='pyscrabble',
    version='1.0',
    author='Armands Gedroics',
    author_email='armands.gedroics@gmail.com',
    url='https://github.com/armands3312/pyscrabble',
    description='Multiplayer word game',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Topic :: Games/Entertainment :: Board Games'
    ],
    packages=['pyscrabble'],
    entry_points={
        'gui_scripts': [
            'pyscrabble = pyscrabble.__main__:main'
        ]
    }
)
