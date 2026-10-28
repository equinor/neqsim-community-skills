"""TEG dehydration plant builder and emission helpers for NeqSim.

This module captures a validated, closed-loop triethylene-glycol (TEG) gas
dehydration flowsheet and the non-obvious settings needed for it to converge.
All inputs and the default feed composition are public and synthetic.

NeqSim (the Java thermodynamic/process engine) is required to build and run the
plant. The helper emission functions only need a NeqSim stream object.
"""

from __future__ import annotations

__all__ = [
    "GAS_COMPONENTS",
    "DEFAULT_FEED",
    "NMVOC",
    "GHG_CH4",
    "build_teg_plant",
    "comp_mass_flows_kg_hr",
    "teg_mass_fraction",
    "glycol_purity_wt",
    "classify_emissions",
]

# Public, synthetic natural-gas component list and a representative composition.
GAS_COMPONENTS = [
    "nitrogen",
    "CO2",
    "methane",
    "ethane",
    "propane",
    "i-butane",
    "n-butane",
    "i-pentane",
    "n-pentane",
    "n-hexane",
    "benzene",
]
DEFAULT_FEED = [
    0.245,
    3.4,
    85.7,
    5.981,
    2.743,
    0.37,
    0.77,
    0.142,
    0.166,
    0.06,
    0.01,
]

# Emission classification buckets.
NMVOC = {
    "ethane",
    "propane",
    "i-butane",
    "n-butane",
    "i-pentane",
    "n-pentane",
    "n-hexane",
    "benzene",
}
GHG_CH4 = {"methane"}


def _jneqsim():
    """Import the NeqSim Java bridge, raising a clear error if unavailable."""
    try:
        from neqsim import jneqsim
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "NeqSim is required for build_teg_plant. Install the 'neqsim' "
            "Python package (which bundles the Java engine)."
        ) from exc
    return jneqsim


def build_teg_plant(
    feed_fractions,
    feed_flow_MSm3_day,
    feed_temp_C,
    feed_pressure_bara,
    absorber_pressure_bara,
    absorber_temp_C,
    teg_flow_kg_hr,
    teg_feed_temp_C,
    lean_teg_purity,
    flash_drum_pressure_bara,
    reboiler_temp_C,
    stripping_gas_Sm3_hr,
    n_absorber_stages,
    stage_efficiency,
    water_mode="saturated",
    water_content_ppm_mol=None,
    saturation_temp_C=None,
    saturation_pressure_bara=None,
    recirculate_stripping_gas=False,
    recycle_blower_discharge_bara=1.4,
    stripping_mode="gas",
    drizo_solvent_kg_hr=150.0,
    drizo_solvent_comp=None,
    drizo_solvent_temp_C=220.0,
    still_pressure_bara=1.2,
    solvent_recovery_temp_C=20.0,
    components=None,
):
    """Build a closed-loop TEG dehydration plant as a NeqSim ProcessSystem.

    ``stripping_mode="gas"`` (default) strips with dry gas (once-through or recirculated).
    ``stripping_mode="drizo"`` builds the Drizo solvent loop used on Oseberg D: flash vapour is
    cooled to ``solvent_recovery_temp_C`` and its condensate returned to the still feed, the still
    overhead is condensed in a three-phase receiver, the recovered hydrocarbon solvent is split at
    a fixed ``drizo_solvent_kg_hr`` (the rest is drained), superheated to ``drizo_solvent_temp_C``
    and fed to the stripper as stripping vapour. ``drizo_solvent_comp`` maps component name to
    mole fraction (default hexane/benzene); ``components`` replaces ``GAS_COMPONENTS`` so heavier
    aromatics (toluene, m-Xylene) can be added, with ``feed_fractions`` aligned to it.

    Returns a tuple ``(process, streams)`` where ``process`` is a NeqSim
    ``ProcessSystem`` ready to run (``process.runAsThread()`` then
    ``thr.join(timeout_ms)``) and ``streams`` is a dict of key stream handles:
    ``dehydratedGas``, ``flashGas``, ``stillVent``, ``leanTEGtoAbs``,
    ``waterDewAnalyser``, ``strippingGas``, ``recircBlower``.

    See the skill SKILL.md for the meaning of each parameter and the validated
    default inputs.
    """
    jneqsim = _jneqsim()

    SystemSrkCPA = jneqsim.thermo.system.SystemSrkCPAstatoil
    ProcessSystem = jneqsim.process.processmodel.ProcessSystem
    Stream = jneqsim.process.equipment.stream.Stream
    StreamSaturatorUtil = jneqsim.process.equipment.util.StreamSaturatorUtil
    Heater = jneqsim.process.equipment.heatexchanger.Heater
    HeatExchanger = jneqsim.process.equipment.heatexchanger.HeatExchanger
    SimpleTEGAbsorber = jneqsim.process.equipment.absorber.SimpleTEGAbsorber
    WaterStripperColumn = jneqsim.process.equipment.absorber.WaterStripperColumn
    DistillationColumn = jneqsim.process.equipment.distillation.DistillationColumn
    Separator = jneqsim.process.equipment.separator.Separator
    Splitter = jneqsim.process.equipment.splitter.Splitter
    Compressor = jneqsim.process.equipment.compressor.Compressor
    ThrottlingValve = jneqsim.process.equipment.valve.ThrottlingValve
    Filter = jneqsim.process.equipment.filter.Filter
    Pump = jneqsim.process.equipment.pump.Pump
    Mixer = jneqsim.process.equipment.mixer.Mixer
    Calculator = jneqsim.process.equipment.util.Calculator
    Recycle = jneqsim.process.equipment.util.Recycle
    WaterDewPointAnalyser = jneqsim.process.measurementdevice.WaterDewPointAnalyser

    p = ProcessSystem()
    comp_names = list(components) if components is not None else list(GAS_COMPONENTS)
    n_comp = len(comp_names) + 2
    drizo = stripping_mode == "drizo"
    if stripping_mode not in ("gas", "drizo"):
        raise ValueError("stripping_mode must be 'gas' or 'drizo'")
    if drizo and recirculate_stripping_gas:
        raise ValueError("recirculate_stripping_gas applies to stripping_mode='gas' only")
    still_P = float(still_pressure_bara)
    ThreePhaseSeparator = jneqsim.process.equipment.separator.ThreePhaseSeparator

    # --- Feed fluid: CPA EOS, TEG added LAST so lean-TEG indices are stable. ---
    feedGas = SystemSrkCPA()
    total_gas = sum(float(f) for f in feed_fractions)
    for name, frac in zip(comp_names, feed_fractions):
        feedGas.addComponent(name, float(frac))
    if water_mode == "specified":
        water_moles = (float(water_content_ppm_mol or 0.0) * 1.0e-6) * total_gas
        feedGas.addComponent("water", water_moles)
    else:
        feedGas.addComponent("water", 0.0)
    feedGas.addComponent("TEG", 0.0)
    feedGas.setMixingRule(10)
    feedGas.setMultiPhaseCheck(False)
    feedGas.init(0)

    dryFeedGas = Stream("dry feed gas", feedGas)
    dryFeedGas.setFlowRate(feed_flow_MSm3_day, "MSm3/day")
    dryFeedGas.setTemperature(feed_temp_C, "C")
    dryFeedGas.setPressure(feed_pressure_bara, "bara")
    p.add(dryFeedGas)

    # --- Feed water conditioning ---
    if water_mode == "specified":
        wetFeedGas = dryFeedGas
    elif saturation_temp_C is not None or saturation_pressure_bara is not None:
        sat_T = saturation_temp_C if saturation_temp_C is not None else feed_temp_C
        sat_P = (
            saturation_pressure_bara
            if saturation_pressure_bara is not None
            else feed_pressure_bara
        )
        satSetter = Heater("saturation TP setter", dryFeedGas)
        satSetter.setOutTemperature(sat_T, "C")
        satSetter.setOutPressure(sat_P, "bara")
        p.add(satSetter)
        gasToSat = Stream("gas at saturation conditions", satSetter.getOutletStream())
        p.add(gasToSat)
        saturator = StreamSaturatorUtil("water saturator", gasToSat)
        p.add(saturator)
        wetFeedGas = Stream("water saturated feed gas", saturator.getOutletStream())
        p.add(wetFeedGas)
    else:
        saturator = StreamSaturatorUtil("water saturator", dryFeedGas)
        p.add(saturator)
        wetFeedGas = Stream("water saturated feed gas", saturator.getOutletStream())
        p.add(wetFeedGas)

    feedTPsetter = Heater("TP of gas to absorber", wetFeedGas)
    feedTPsetter.setOutPressure(absorber_pressure_bara, "bara")
    feedTPsetter.setOutTemperature(absorber_temp_C, "C")
    p.add(feedTPsetter)
    feedToAbsorber = Stream("feed to TEG absorber", feedTPsetter.getOutletStream())
    p.add(feedToAbsorber)

    # --- Lean TEG feed (TEG is the last component). ---
    feedTEG = feedGas.clone()
    leanComp = [0.0] * n_comp
    leanComp[-2] = 1.0 - lean_teg_purity
    leanComp[-1] = lean_teg_purity
    feedTEG.setMolarComposition(leanComp)
    TEGFeed = Stream("TEG feed", feedTEG)
    TEGFeed.setFlowRate(teg_flow_kg_hr, "kg/hr")
    TEGFeed.setTemperature(teg_feed_temp_C, "C")
    TEGFeed.setPressure(absorber_pressure_bara, "bara")
    p.add(TEGFeed)

    # --- Absorber ---
    absorber = SimpleTEGAbsorber("TEG absorber")
    absorber.addGasInStream(feedToAbsorber)
    absorber.addSolventInStream(TEGFeed)
    absorber.setNumberOfStages(int(n_absorber_stages))
    absorber.setStageEfficiency(stage_efficiency)
    absorber.setInternalDiameter(2.240)
    p.add(absorber)

    dehydratedGas = Stream("dry gas from absorber", absorber.getGasOutStream())
    p.add(dehydratedGas)
    richTEG = Stream("rich TEG from absorber", absorber.getLiquidOutStream())
    p.add(richTEG)

    waterDewAnalyser = WaterDewPointAnalyser("water dew point analyser", dehydratedGas)
    waterDewAnalyser.setReferencePressure(feed_pressure_bara)
    p.add(waterDewAnalyser)

    # --- Rich TEG let-down, pre-heat and degassing ---
    flashValve = ThrottlingValve("Rich TEG HP flash valve", richTEG)
    flashValve.setOutletPressure(flash_drum_pressure_bara)
    p.add(flashValve)

    richPreheat = Heater("rich TEG preheater", flashValve.getOutletStream())
    p.add(richPreheat)

    heatEx2 = HeatExchanger("rich TEG heat exchanger 1", richPreheat.getOutletStream())
    heatEx2.setGuessOutTemperature(273.15 + 62.0)
    heatEx2.setUAvalue(2224.0)
    p.add(heatEx2)

    flashSep = Separator("degassing separator", heatEx2.getOutStream(0))
    flashSep.setInternalDiameter(1.2)
    p.add(flashSep)
    flashGas = Stream("gas from degassing separator", flashSep.getGasOutStream())
    p.add(flashGas)
    flashLiquid = Stream("liquid from degassing separator", flashSep.getLiquidOutStream())
    p.add(flashLiquid)

    fineFilter = Filter("TEG fine filter", flashLiquid)
    fineFilter.setDeltaP(0.0, "bara")
    p.add(fineFilter)

    if drizo:
        # Solvent recovery: flash vapour condensed, liquid returned to the still feed.
        srCooler = Heater("solvent recovery condenser", flashGas)
        srCooler.setOutTemperature(273.15 + solvent_recovery_temp_C)
        p.add(srCooler)
        srDrum = Separator("solvent recovery drum", srCooler.getOutletStream())
        p.add(srDrum)
        flashVent = Stream("flash gas to flare", srDrum.getGasOutStream())
        p.add(flashVent)
        srLiquid = Stream("solvent recovery liquid", srDrum.getLiquidOutStream())
        p.add(srLiquid)
        retFluid = feedGas.clone()
        retComp = [0.0] * n_comp
        retComp[comp_names.index("n-hexane")] = 1.0
        retFluid.setMolarComposition(retComp)
        srReturn = Stream("solvent recovery return", retFluid)
        srReturn.setFlowRate(1.0e-3, "kg/hr")
        srReturn.setTemperature(solvent_recovery_temp_C, "C")
        srReturn.setPressure(flash_drum_pressure_bara, "bara")
        p.add(srReturn)
    else:
        flashVent = flashGas

    heatEx = HeatExchanger("lean/rich TEG heat-exchanger", fineFilter.getOutletStream())
    heatEx.setGuessOutTemperature(273.15 + 130.0)
    heatEx.setUAvalue(8316.0)
    p.add(heatEx)

    if drizo:
        richMixer = Mixer("rich TEG + recovered solvent mixer")
        richMixer.addStream(heatEx.getOutStream(0))
        richMixer.addStream(srReturn)
        p.add(richMixer)
        stillFeed = richMixer.getOutletStream()
    else:
        stillFeed = heatEx.getOutStream(0)
    flashValve2 = ThrottlingValve("Rich TEG LP flash valve", stillFeed)
    flashValve2.setOutletPressure(still_P)
    p.add(flashValve2)
    if drizo:
        recycleSolventRecovery = Recycle("solvent recovery recycle")
        recycleSolventRecovery.addStream(srLiquid)
        recycleSolventRecovery.setOutletStream(srReturn)
        p.add(recycleSolventRecovery)

    # --- Stripping gas (Drizo: initial guess of the superheated solvent vapour) ---
    stripGas = feedGas.clone()
    if drizo:
        sol = drizo_solvent_comp or {"n-hexane": 0.7, "benzene": 0.3}
        tot = float(sum(sol.values()))
        stripGas.setMolarComposition(
            [float(sol.get(n, 0.0)) / tot for n in comp_names] + [0.0, 0.0]
        )
    strippingGas = Stream("stripGas", stripGas)
    if drizo:
        strippingGas.setFlowRate(float(drizo_solvent_kg_hr), "kg/hr")
        strippingGas.setTemperature(float(drizo_solvent_temp_C), "C")
    else:
        strippingGas.setFlowRate(stripping_gas_Sm3_hr, "Sm3/hr")
        strippingGas.setTemperature(78.3, "C")
    strippingGas.setPressure(still_P, "bara")
    p.add(strippingGas)
    gasToReboiler = strippingGas.clone("gas to reboiler")
    p.add(gasToReboiler)

    # --- TEG regeneration column (loosened tolerances for convergence) ---
    column = DistillationColumn("TEG regeneration column", 1, True, True)
    column.setTemperatureTolerance(5.0e-2)
    column.setMassBalanceTolerance(2.0e-1)
    column.setEnthalpyBalanceTolerance(2.0e-1)
    column.addFeedStream(flashValve2.getOutletStream(), 0 if drizo else 1)
    column.getReboiler().setOutTemperature(273.15 + reboiler_temp_C)
    column.getCondenser().setOutTemperature(273.15 + (93.0 if drizo else 85.0))
    if drizo:
        column.getReboiler().addStream(gasToReboiler)
        column.setTopPressure(still_P - 0.2)
    else:
        column.getTray(1).addStream(gasToReboiler)
        column.setTopPressure(still_P)
    column.setBottomPressure(still_P)
    column.setInternalDiameter(0.56)
    p.add(column)

    coolerRegenGas = Heater("regen gas cooler", column.getGasOutStream())
    coolerRegenGas.setOutTemperature(
        273.15 + (solvent_recovery_temp_C if drizo else 47.0)
    )
    p.add(coolerRegenGas)

    solventExcess = None
    solventHeater = None
    if drizo:
        sepRegenGas = ThreePhaseSeparator("regen gas separator", coolerRegenGas.getOutletStream())
        p.add(sepRegenGas)
        waterToTreatment = Stream("water to process or drain", sepRegenGas.getWaterOutStream())
        p.add(waterToTreatment)
        recoveredSolvent = Stream("recovered solvent", sepRegenGas.getOilOutStream())
        p.add(recoveredSolvent)
        solventSplit = Splitter("solvent split", recoveredSolvent)
        solventSplit.setSplitNumber(2)
        solventSplit.setFlowRates([float(drizo_solvent_kg_hr), -1.0], "kg/hr")
        p.add(solventSplit)
        solventExcess = Stream("excess solvent to closed drain", solventSplit.getSplitStream(1))
        p.add(solventExcess)
        solventHeater = Heater("solvent superheater", solventSplit.getSplitStream(0))
        solventHeater.setOutPressure(still_P + 0.3, "bara")
        solventHeater.setOutTemperature(273.15 + float(drizo_solvent_temp_C))
        p.add(solventHeater)
        stillVent = Stream("still vent", sepRegenGas.getGasOutStream())
        p.add(stillVent)
        recircBlower = None
        recircHeater = None
    else:
        sepRegenGas = Separator("regen gas separator", coolerRegenGas.getOutletStream())
        p.add(sepRegenGas)
        waterToTreatment = Stream(
            "water/HC to process or flare drum", sepRegenGas.getLiquidOutStream()
        )
        p.add(waterToTreatment)

    # --- Still vent: vented once-through, or recirculated as stripping gas ---
    if drizo:
        pass
    elif recirculate_stripping_gas:
        recircSplit = Splitter("stripping gas recirc split", sepRegenGas.getGasOutStream())
        recircSplit.setFlowRates([float(stripping_gas_Sm3_hr), -1.0], "Sm3/hr")
        p.add(recircSplit)
        stillVent = Stream(
            "still vent (flare/vent/recompression)", recircSplit.getSplitStream(1)
        )
        p.add(stillVent)
        recircBlower = Compressor(
            "stripping gas recycle blower", recircSplit.getSplitStream(0)
        )
        recircBlower.setOutletPressure(recycle_blower_discharge_bara)
        recircBlower.setIsentropicEfficiency(0.75)
        p.add(recircBlower)
        recircHeater = Heater("stripping gas recirc heater", recircBlower.getOutletStream())
        recircHeater.setOutTemperature(273.15 + 78.3)
        p.add(recircHeater)
    else:
        recircBlower = None
        recircHeater = None
        stillVent = Stream(
            "still vent (flare/vent/recompression)", sepRegenGas.getGasOutStream()
        )
        p.add(stillVent)

    # --- Deep stripping for lean TEG purity ---
    stripper = WaterStripperColumn("TEG stripper")
    stripper.addSolventInStream(column.getLiquidOutStream())
    stripper.addGasInStream(strippingGas)
    if drizo:
        stripper.setNumberOfStages(4)
        stripper.setStageEfficiency(1.0)
    else:
        stripper.setNumberOfStages(2)
        stripper.setStageEfficiency(1.0)
    p.add(stripper)

    recycleStripGas = Recycle("stripping gas recirc")
    recycleStripGas.addStream(stripper.getGasOutStream())
    recycleStripGas.setOutletStream(gasToReboiler)
    if drizo:
        recycleStripGas.setMaxIterations(60)
    p.add(recycleStripGas)

    if recirculate_stripping_gas:
        recycleStrippingMakeup = Recycle("stripping gas makeup recycle")
        recycleStrippingMakeup.addStream(recircHeater.getOutletStream())
        recycleStrippingMakeup.setOutletStream(strippingGas)
        recycleStrippingMakeup.setPriority(recycleStripGas.getPriority())
        p.add(recycleStrippingMakeup)
    if drizo:
        recycleSolventLoop = Recycle("solvent loop recycle")
        recycleSolventLoop.addStream(solventHeater.getOutletStream())
        recycleSolventLoop.setOutletStream(strippingGas)
        recycleSolventLoop.setPriority(recycleStripGas.getPriority())
        p.add(recycleSolventLoop)

    heatEx.setFeedStream(1, stripper.getLiquidOutStream())

    bufferTank = Heater("TEG buffer tank", heatEx.getOutStream(1))
    bufferTank.setOutTemperature(273.15 + 90.5)
    p.add(bufferTank)

    leanPumpLP = Pump("lean TEG LP pump", bufferTank.getOutletStream())
    leanPumpLP.setOutletPressure(3.0)
    leanPumpLP.setIsentropicEfficiency(0.75)
    p.add(leanPumpLP)

    heatEx2.setFeedStream(1, leanPumpLP.getOutletStream())

    coolerLeanTEG = Heater("lean TEG cooler", heatEx2.getOutStream(1))
    coolerLeanTEG.setOutTemperature(273.15 + teg_feed_temp_C)
    p.add(coolerLeanTEG)

    leanPumpHP = Pump("lean TEG HP pump", coolerLeanTEG.getOutletStream())
    leanPumpHP.setOutletPressure(absorber_pressure_bara)
    leanPumpHP.setIsentropicEfficiency(0.75)
    p.add(leanPumpHP)

    leanTEGtoAbs = Stream("lean TEG to absorber", leanPumpHP.getOutletStream())
    p.add(leanTEGtoAbs)

    # --- TEG makeup sized from TEG lost in the product/vent/water draws ---
    pureTEG = feedGas.clone()
    makeupComp = [0.0] * n_comp
    makeupComp[-1] = 1.0
    pureTEG.setMolarComposition(makeupComp)
    makeupTEG = Stream("makeup TEG", pureTEG)
    makeupTEG.setFlowRate(1e-6, "kg/hr")
    makeupTEG.setTemperature(teg_feed_temp_C, "C")
    makeupTEG.setPressure(absorber_pressure_bara, "bara")
    p.add(makeupTEG)

    makeupCalc = Calculator("TEG makeup calculator")
    makeupCalc.addInputVariable(dehydratedGas)
    makeupCalc.addInputVariable(flashVent)
    makeupCalc.addInputVariable(stillVent)
    makeupCalc.addInputVariable(waterToTreatment)
    if solventExcess is not None:
        makeupCalc.addInputVariable(solventExcess)
    makeupCalc.setOutputVariable(makeupTEG)
    p.add(makeupCalc)

    makeupMixer = Mixer("makeup mixer")
    makeupMixer.addStream(leanTEGtoAbs)
    makeupMixer.addStream(makeupTEG)
    p.add(makeupMixer)

    recycleLeanTEG = Recycle("lean TEG recycle")
    recycleLeanTEG.addStream(makeupMixer.getOutletStream())
    recycleLeanTEG.setOutletStream(TEGFeed)
    recycleLeanTEG.setPriority(200)
    recycleLeanTEG.setDownstreamProperty("flow rate")
    p.add(recycleLeanTEG)

    # Couple the rich preheater duty to the regeneration condenser energy stream.
    richPreheat.setEnergyStream(column.getCondenser().getEnergyStream())

    streams = {
        "dehydratedGas": dehydratedGas,
        "flashGas": flashGas,
        "stillVent": stillVent,
        "leanTEGtoAbs": leanTEGtoAbs,
        "waterDewAnalyser": waterDewAnalyser,
        "strippingGas": strippingGas,
        "recircBlower": recircBlower,
        "flashVent": flashVent,
        "waterToTreatment": waterToTreatment,
        "solventExcess": solventExcess,
        "solventHeater": solventHeater,
        "column": column,
    }
    return p, streams


def comp_mass_flows_kg_hr(stream):
    """Return a dict of per-component mass flow (kg/hr) for a NeqSim stream."""
    fluid = stream.getFluid()
    total = stream.getFlowRate("kg/hr")
    n = fluid.getNumberOfComponents()
    zM = []
    names = []
    for i in range(n):
        c = fluid.getComponent(i)
        names.append(str(c.getComponentName()))
        zM.append(c.getz() * c.getMolarMass())
    s = sum(zM)
    if s <= 0:
        return {names[i]: 0.0 for i in range(n)}
    return {names[i]: (zM[i] / s) * total for i in range(n)}


def teg_mass_fraction(stream):
    """Return the TEG weight percent of a NeqSim stream (all components in the denominator)."""
    flows = comp_mass_flows_kg_hr(stream)
    tot = sum(flows.values())
    return 100.0 * flows.get("TEG", 0.0) / tot if tot > 0 else 0.0


def glycol_purity_wt(stream):
    """Return TEG/(TEG+water) in weight percent, the plant's "wt% glycol" lean/rich basis.

    Use this, not ``teg_mass_fraction``, for lean-TEG quality when hydrocarbons (Drizo solvent,
    dissolved BTEX) are present in the liquid.
    """
    flows = comp_mass_flows_kg_hr(stream)
    denom = flows.get("TEG", 0.0) + flows.get("water", 0.0)
    return 100.0 * flows.get("TEG", 0.0) / denom if denom > 0 else 0.0


def classify_emissions(stream):
    """Classify stream mass flows into emission buckets (kg/hr).

    Returns a dict with ``NMVOC``, ``methane``, ``CO2``, ``water``, ``TEG``,
    ``benzene`` and ``total`` mass flows.
    """
    flows = comp_mass_flows_kg_hr(stream)
    out = {
        "NMVOC": sum(v for k, v in flows.items() if k in NMVOC),
        "methane": sum(v for k, v in flows.items() if k in GHG_CH4),
        "CO2": flows.get("CO2", 0.0),
        "water": flows.get("water", 0.0),
        "TEG": flows.get("TEG", 0.0),
        "benzene": flows.get("benzene", 0.0),
    }
    out["total"] = sum(flows.values())
    return out
