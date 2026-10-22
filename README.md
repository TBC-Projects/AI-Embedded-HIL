# AI Embedded Hardware-in-the-Loop

## Introduction
This document is intended to provide a comprehensive overview of our project's developments and serve as a reference tool for new members joining our team.

This report serves two primary functions:

1. **Project Review:** The document provides details on our established objectives, achievements, encountered challenges, key learnings, and prospective future plans. This reflective evaluation allows our team to track progress, make necessary adjustments, and maintain a clear vision moving forward.
2. **New Member Orientation:** The report also serves as a detailed onboarding guide designed to assist new members in understanding the project's context, objectives, and intricacies. We intend this guide to expedite the acclimatization process and equip newcomers with the necessary knowledge to contribute effectively in the forthcoming semester. Orientation slides: https://docs.google.com/presentation/d/1kqiqQ6VsCJaMvE94yqhtiwX4twRjIrdG3Ff06LFMH-U/edit?usp=sharing

## About the Project

* Project Title: AI Embedded Hardware-in-the-Loop
* Project Purpose: Autonomously write bare-metal C/C++ for a target microcontroller, flash it onto physical hardware, and verify real-time behavior with FPGA-assisted hardware-in-the-loop testing. When a run fails, the system uses the captured trace to revise the source until the checks pass.
* Brief Description: An orchestration engine turns a hardware specification into firmware. A runner cross-compiles and flashes a Raspberry Pi Zero W. A PYNQ-Z2 FPGA records pin timing and logic state and returns a trace for the next revision. Inspired by [Sentinel](https://devpost.com/software/sentinel-c8ki50).
* Contributors Involved: name, name, name
* Git Repo Link: https://github.com/TBC-Projects/AI-Embedded-HIL

## Accomplishments


## Challenges Faced

## Potential Improvements


## Relevant Resources


## Other Information

* Define Abbreviations
  * TBC - The Boring Club
  * HIL - Hardware-in-the-Loop
  * FPGA - Field-Programmable Gate Array
  * GPIO - General-Purpose Input/Output
  * UART - Universal Asynchronous Receiver-Transmitter
* Team Leads
  1. Adelin Ma
  2. Elias Assalif
  3. Ruiqi Liu
