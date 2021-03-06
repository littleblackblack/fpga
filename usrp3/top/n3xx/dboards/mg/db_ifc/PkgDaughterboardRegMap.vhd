-------------------------------------------------------------------------------
--
-- File: PkgDaughterboardRegMap.vhd
-- Author: Autogenerated by XmlParse
-- Original Project: --
-- Date: --
--
-------------------------------------------------------------------------------
-- Copyright 2017 Ettus Research, A National Instruments Company
-- SPDX-License-Identifier: LGPL-3.0
-------------------------------------------------------------------------------
--
-- Purpose:
--   The constants in this file are autogenerated by XmlParse and should
-- be used by testbench code to access specific register fields.
--
-------------------------------------------------------------------------------

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

package PkgDaughterboardRegMap is

--===============================================================================
-- A numerically ordered list of registers and their VHDL source files
--===============================================================================

  -- DaughterboardId : 0x630 (DaughterboardRegs.vhd)

--===============================================================================
-- RegTypes
--===============================================================================

--===============================================================================
-- Register Group StaticControl
--===============================================================================

  -- DaughterboardId Register (from DaughterboardRegs.vhd)
  constant kDaughterboardId : integer := 16#630#; -- Register Offset
  constant kDaughterboardIdSize: integer := 32;  -- register width in bits
  constant kDaughterboardIdMask : std_logic_vector(31 downto 0) := X"0001ffff";
  constant kDbIdValSize       : integer := 16;  --DaughterboardId:DbIdVal
  constant kDbIdValMsb        : integer := 15;  --DaughterboardId:DbIdVal
  constant kDbIdVal           : integer :=  0;  --DaughterboardId:DbIdVal
  constant kSlotIdValSize       : integer :=  1;  --DaughterboardId:SlotIdVal
  constant kSlotIdValMsb        : integer := 16;  --DaughterboardId:SlotIdVal
  constant kSlotIdVal           : integer := 16;  --DaughterboardId:SlotIdVal

end package;

package body PkgDaughterboardRegMap is

  -- function kDaughterboardIdRec not implemented because PkgXReg in this project does not support XReg2_t.

end package body;
