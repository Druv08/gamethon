#include "Core/PTKWaveManager.h"

#include "Characters/PTKEnemyCharacter.h"
#include "Components/PTKHealthComponent.h"
#include "Core/PTKBattlefield.h"
#include "Core/PTKGuardBase.h"
#include "Core/PTKGameModeBase.h"
#include "Analytics/PTKAdaptiveDirector.h"
#include "Analytics/PTKAnalyticsSubsystem.h"
#include "Core/PTKSpawnPortal.h"
#include "EngineUtils.h"
#include "ProtectTheKing2D.h"

APTKWaveManager::APTKWaveManager()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

APTKWaveManager* APTKWaveManager::Get(const UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<APTKWaveManager> It(const_cast<UWorld*>(World)); It; ++It)
	{
		return *It;
	}
	return nullptr;
}

void APTKWaveManager::BeginPlay()
{
	Super::BeginPlay();

	if (Waves.Num() == 0)
	{
		BuildDefaultWaves();
	}
	// A seed handed over by Restart wins; then an authored one; then a fresh
	// random one. Restart is the only thing that ever supplies one, and it
	// supplies the seed the previous run used - which is what makes Restart a
	// replay rather than just another random run.
	const int32 Carried = APTKGameModeBase::ConsumePendingWaveSeed();
	ActiveSeed = Carried != 0 ? Carried
		: (RandomSeed != 0 ? RandomSeed : FMath::Rand());
	Stream.Initialize(ActiveSeed);
	UE_LOG(LogPTK, Log, TEXT("WAVES | seed %d%s"), ActiveSeed,
		Carried != 0 ? TEXT(" (replayed)") : TEXT(""));

	if (UPTKAdaptiveDirector* Director = UPTKAdaptiveDirector::Get(GetWorld()))
	{
		// Same seed as the wave manager, so a Restart replays the director's
		// exploration rolls as well as the wave rolls.
		Director->SeedFrom(ActiveSeed);
	}

	UE_LOG(LogPTK, Log, TEXT("WAVES | %d waves configured | waiting for start"), Waves.Num());
}

// ---------------------------------------------------------------------------
// The five-wave prototype from the spec.
//
// Counts climb gently while the MIX does the real work: wave 1 is a crowd of
// one weak thing, wave 5 is a smaller number of five different things arriving
// from three sides at once. That is a harder fight at a similar body count,
// which is what keeps late waves threatening without turning into a slideshow.
// ---------------------------------------------------------------------------

void APTKWaveManager::BuildDefaultWaves()
{
	auto Entry = [this](const TCHAR* Id, int32 Weight)
	{
		FPTKWaveEntry E;
		if (const TSubclassOf<APTKEnemyCharacter>* Found = EnemyTypes.Find(FName(Id)))
		{
			E.EnemyClass = *Found;
		}
		E.Weight = Weight;
		return E;
	};

	auto Wave = [this](const TCHAR* Name, int32 Count, int32 Portals, float Interval,
		std::initializer_list<TPair<const TCHAR*, int32>> Mix)
	{
		FPTKWaveDefinition W;
		W.WaveName = FText::FromString(Name);
		W.EnemyCount = Count;
		W.PortalCount = Portals;
		W.SpawnInterval = Interval;
		for (const TPair<const TCHAR*, int32>& M : Mix)
		{
			FPTKWaveEntry E;
			if (const TSubclassOf<APTKEnemyCharacter>* Found = EnemyTypes.Find(FName(M.Key)))
			{
				E.EnemyClass = *Found;
			}
			E.Weight = M.Value;
			W.Composition.Add(E);
		}
		Waves.Add(MoveTemp(W));
	};

	// PortalCount is at least 2 from the very first wave. Each corner feeds two
	// lanes ending at different bases, so two corners is four lanes and four
	// defenders under pressure - which is the point. A single-corner wave would
	// leave three quarters of the map idle and make the whole lane system look
	// like it was not working.
	Wave(TEXT("Probe"), 12, 2, 0.40f,
		{ {TEXT("SwarmNode"), 10}, {TEXT("Infiltrator"), 1} });

	Wave(TEXT("Breach"), 16, 2, 0.35f,
		{ {TEXT("SwarmNode"), 6}, {TEXT("Infiltrator"), 4} });

	Wave(TEXT("Intrusion"), 20, 3, 0.32f,
		{ {TEXT("SwarmNode"), 5}, {TEXT("Infiltrator"), 4}, {TEXT("Hijacker"), 3} });

	Wave(TEXT("Escalation"), 24, 3, 0.30f,
		{ {TEXT("SwarmNode"), 4}, {TEXT("Infiltrator"), 3}, {TEXT("Hijacker"), 3},
		  {TEXT("Encrypter"), 1}, {TEXT("Exfiltrator"), 3} });

	Wave(TEXT("Full Assault"), 30, 4, 0.26f,
		{ {TEXT("SwarmNode"), 3}, {TEXT("Infiltrator"), 3}, {TEXT("Hijacker"), 3},
		  {TEXT("Encrypter"), 2}, {TEXT("Exfiltrator"), 3} });
}

// ---------------------------------------------------------------------------
// Run control
// ---------------------------------------------------------------------------

void APTKWaveManager::StartRun()
{
	if (Phase != EPTKWavePhase::Idle)
	{
		return;
	}
	if (Waves.Num() == 0)
	{
		UE_LOG(LogPTK, Warning, TEXT("WAVES | start requested with no waves configured"));
		return;
	}
	UE_LOG(LogPTK, Log, TEXT("WAVES | run started"));
	BeginWave(1);
}

void APTKWaveManager::StopRun()
{
	// Complete is preserved rather than overwritten. Clearing the last wave
	// ends the run, and ending the run stops the wave system - so victory
	// arrives here immediately after Complete is set. Treating that as "halted"
	// would throw away the fact that every wave was beaten, which is what the
	// HUD reads to say so.
	if (Phase == EPTKWavePhase::Stopped || Phase == EPTKWavePhase::Complete)
	{
		return;
	}
	Phase = EPTKWavePhase::Stopped;
	PendingRoster.Reset();
	for (const TObjectPtr<APTKSpawnPortal>& Portal : ActivePortals)
	{
		if (Portal)
		{
			Portal->ClearWarning();
		}
	}
	ActivePortals.Reset();
	UE_LOG(LogPTK, Warning, TEXT("WAVES | run stopped"));
}

void APTKWaveManager::BeginWave(int32 Wave)
{
	if (!Waves.IsValidIndex(Wave - 1))
	{
		return;
	}
	CurrentWave = Wave;
	const FPTKWaveDefinition& Definition = Waves[Wave - 1];

	// Ask the director how this wave should attack, BEFORE the corners are
	// chosen - its answer is what weights that choice. Adapting happens here,
	// between waves, and nowhere else: once bodies are on the field nothing
	// re-steers them.
	FPTKDirectorPlan Plan;
	if (UPTKAdaptiveDirector* Director = UPTKAdaptiveDirector::Get(GetWorld()))
	{
		Plan = Director->BuildPlan(Wave);
		Director->LogPlan();
	}

	// Choose which corners this wave uses, at random, without repeats.
	ActivePortals.Reset();
	TArray<APTKSpawnPortal*> All;
	if (const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		for (const TObjectPtr<APTKSpawnPortal>& Portal : Field->GetPortals())
		{
			if (Portal)
			{
				All.Add(Portal);
			}
		}
	}
	if (All.Num() == 0)
	{
		UE_LOG(LogPTK, Error, TEXT("WAVES | no spawn portals in the level - wave %d cannot arrive"), Wave);
		Phase = EPTKWavePhase::Stopped;
		return;
	}

	const int32 Wanted = FMath::Clamp(
		FMath::Max(Definition.PortalCount, Plan.MinimumPortals), 1, All.Num());

	// Corners are drawn weighted by how much pressure the plan puts on the
	// lanes they feed, so a strategy that wants a particular front is likely -
	// not guaranteed - to get it. Weighted rather than deterministic keeps
	// repeated runs from becoming identical.
	const APTKBattlefield* const PlanField = APTKBattlefield::Get(GetWorld());
	for (int32 i = 0; i < Wanted && All.Num() > 0; ++i)
	{
		float Total = 0.0f;
		TArray<float> Weights;
		Weights.Reserve(All.Num());
		for (const APTKSpawnPortal* Portal : All)
		{
			float Weight = 0.0f;
			for (const FPTKLanePlan& Lane : Plan.Lanes)
			{
				const FPTKLaneRoute* Route = PlanField ? PlanField->FindRoute(Lane.LaneId) : nullptr;
				if (Route && Portal && Route->PortalId == Portal->GetPortalId())
				{
					Weight += FMath::Max(Lane.Pressure, 0.0f);
				}
			}
			// A floor, so a corner the plan ignores can still be drawn and no
			// part of the map becomes permanently safe.
			Weight = FMath::Max(Weight, 0.05f);
			Weights.Add(Weight);
			Total += Weight;
		}

		int32 Pick = 0;
		float Roll = Stream.FRand() * Total;
		for (int32 j = 0; j < All.Num(); ++j)
		{
			Roll -= Weights[j];
			if (Roll <= 0.0f)
			{
				Pick = j;
				break;
			}
		}
		ActivePortals.Add(All[Pick]);
		All.RemoveAt(Pick);
	}

	RollComposition(Definition, PendingRoster);

	// Collect every lane the chosen corners feed, then shuffle so the dealing
	// order differs run to run. Enemies are dealt across these in turn, which is
	// what guarantees a wave pressures several bases rather than one.
	ActiveRoutes.Reset();
	RouteCursor = 0;
	if (const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		for (const TObjectPtr<APTKSpawnPortal>& Portal : ActivePortals)
		{
			if (Portal)
			{
				ActiveRoutes.Append(Field->GetRouteIdsForPortal(Portal->GetPortalId()));
			}
		}
		for (int32 i = ActiveRoutes.Num() - 1; i > 0; --i)
		{
			ActiveRoutes.Swap(i, Stream.RandRange(0, i));
		}
	}

	FString PortalNames;
	for (const TObjectPtr<APTKSpawnPortal>& Portal : ActivePortals)
	{
		if (Portal)
		{
			Portal->BeginWarning(WarningDuration);
			PortalNames += (PortalNames.IsEmpty() ? TEXT("") : TEXT(", ")) + Portal->GetPortalId().ToString();
		}
	}

	FString RouteNames;
	for (const FName& RouteId : ActiveRoutes)
	{
		RouteNames += (RouteNames.IsEmpty() ? TEXT("") : TEXT(", ")) + RouteId.ToString();
	}
	UE_LOG(LogPTK, Log, TEXT("WAVE %d LANES | %s"), Wave, *RouteNames);

	Phase = EPTKWavePhase::Warning;
	PhaseTimer = WarningDuration;
	SpawnTimer = 0.0f;

	if (UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld()))
	{
		Analytics->NotifyWaveBegan(Wave);
	}

	UE_LOG(LogPTK, Log, TEXT("WAVE %d/%d INCOMING | %d enemies from %s | HP x%.2f DMG x%.2f"),
		Wave, Waves.Num(), PendingRoster.Num(), *PortalNames,
		GetHealthScaleForWave(Wave), GetDamageScaleForWave(Wave));
}

void APTKWaveManager::RollComposition(const FPTKWaveDefinition& Definition,
	TArray<TSubclassOf<APTKEnemyCharacter>>& OutRoster)
{
	OutRoster.Reset();

	int32 TotalWeight = 0;
	for (const FPTKWaveEntry& Entry : Definition.Composition)
	{
		if (Entry.EnemyClass && Entry.Weight > 0)
		{
			TotalWeight += Entry.Weight;
		}
	}
	if (TotalWeight <= 0)
	{
		UE_LOG(LogPTK, Warning, TEXT("WAVES | wave %d has no usable composition"), CurrentWave);
		return;
	}

	for (int32 i = 0; i < Definition.EnemyCount; ++i)
	{
		int32 Roll = Stream.RandRange(0, TotalWeight - 1);
		for (const FPTKWaveEntry& Entry : Definition.Composition)
		{
			if (!Entry.EnemyClass || Entry.Weight <= 0)
			{
				continue;
			}
			Roll -= Entry.Weight;
			if (Roll < 0)
			{
				OutRoster.Add(Entry.EnemyClass);
				break;
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Tick: the phase machine
// ---------------------------------------------------------------------------

void APTKWaveManager::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (Phase == EPTKWavePhase::Idle || Phase == EPTKWavePhase::Complete
		|| Phase == EPTKWavePhase::Stopped)
	{
		return;
	}

	PruneDead();

	switch (Phase)
	{
	case EPTKWavePhase::Warning:
		PhaseTimer -= DeltaSeconds;
		if (PhaseTimer <= 0.0f)
		{
			PhaseTimer = 0.0f;
			Phase = EPTKWavePhase::Spawning;
			SpawnTimer = 0.0f;
			UE_LOG(LogPTK, Log, TEXT("WAVE %d SPAWNING"), CurrentWave);
		}
		break;

	case EPTKWavePhase::Spawning:
	{
		const FPTKWaveDefinition& Definition = Waves[CurrentWave - 1];
		SpawnTimer -= DeltaSeconds;
		while (SpawnTimer <= 0.0f && PendingRoster.Num() > 0)
		{
			// The roster still carries the wave's BUDGET - one entry per body,
			// popped here - but which lane this body walks and what it is are
			// the director's to decide. The count it was built with is never
			// changed, so an adapting wave is never a bigger wave.
			PendingRoster.Pop(EAllowShrinking::No);
			SpawnOne(nullptr);
			SpawnTimer += FMath::Max(Definition.SpawnInterval, 0.01f);
		}
		if (PendingRoster.Num() == 0)
		{
			Phase = EPTKWavePhase::Fighting;
			for (const TObjectPtr<APTKSpawnPortal>& Portal : ActivePortals)
			{
				if (Portal)
				{
					Portal->ClearWarning();
				}
			}
			UE_LOG(LogPTK, Log, TEXT("WAVE %d FULLY DEPLOYED | %d on the field"),
				CurrentWave, GetEnemiesRemaining());
		}
		break;
	}

	case EPTKWavePhase::Fighting:
		if (GetEnemiesRemaining() == 0)
		{
			// Freeze the record before the phase changes, so the snapshot is
			// of the wave that was just fought rather than of whatever the
			// next one has already begun doing.
			if (UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld()))
			{
				Analytics->NotifyWaveEnded(CurrentWave);

				// Score the plan that just ran against what it achieved. Done
				// after the freeze so the reward is read from the finished
				// snapshot rather than from counters still being written to.
				if (UPTKAdaptiveDirector* Director = UPTKAdaptiveDirector::Get(GetWorld()))
				{
					Director->LearnFromWave(Analytics->GetLastSnapshot());
				}
			}
			if (CurrentWave >= Waves.Num())
			{
				Phase = EPTKWavePhase::Complete;
				PhaseTimer = 0.0f;
				UE_LOG(LogPTK, Log, TEXT("WAVES | all %d waves cleared"), Waves.Num());
				if (APTKGameModeBase* Mode = GetWorld()->GetAuthGameMode<APTKGameModeBase>())
				{
					Mode->NotifyWavesCleared();
				}
			}
			else
			{
				Phase = EPTKWavePhase::Intermission;
				PhaseTimer = IntermissionDuration;
				UE_LOG(LogPTK, Log, TEXT("WAVE %d CLEARED | next in %.0fs"), CurrentWave, PhaseTimer);

				// Decide the next wave NOW rather than when it starts, so the
				// analysis panel shown during the intermission is reporting the
				// real decision instead of a prediction of one.
				if (UPTKAdaptiveDirector* Director = UPTKAdaptiveDirector::Get(GetWorld()))
				{
					Director->BuildPlan(CurrentWave + 1);
					Director->LogWaveBlock(CurrentWave + 1);
				}
			}
		}
		break;

	case EPTKWavePhase::Intermission:
		PhaseTimer -= DeltaSeconds;
		if (PhaseTimer <= 0.0f)
		{
			BeginWave(CurrentWave + 1);
		}
		break;

	default:
		break;
	}
}

bool APTKWaveManager::SpawnOne(TSubclassOf<APTKEnemyCharacter> EnemyClass)
{
	// A null class is not an error here: it means "director's choice", resolved
	// below once the lane is known.
	if (ActivePortals.Num() == 0)
	{
		return false;
	}

	// Deal the next lane, then spawn at THAT lane's portal - not the other way
	// round. Choosing the portal first and the lane second would let the two
	// disagree and put an enemy on a route starting in a different corner.
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	FName RouteId = PickLaneFromPlan();
	APTKSpawnPortal* Portal = nullptr;

	if (Field && !RouteId.IsNone())
	{
		if (const FPTKLaneRoute* Route = Field->FindRoute(RouteId))
		{
			for (const TObjectPtr<APTKSpawnPortal>& Candidate : ActivePortals)
			{
				if (Candidate && Candidate->GetPortalId() == Route->PortalId)
				{
					Portal = Candidate;
					break;
				}
			}
		}
	}

	// What walks down it. Chosen after the lane, because the director's
	// composition bias is per-lane.
	if (!EnemyClass)
	{
		EnemyClass = PickEnemyForLane(RouteId);
	}
	if (!EnemyClass)
	{
		return false;
	}
	if (!Portal)
	{
		Portal = ActivePortals[Stream.RandRange(0, ActivePortals.Num() - 1)];
		RouteId = NAME_None;
	}
	if (!Portal)
	{
		return false;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;

	const FVector Where = Portal->PickSpawnPoint(Stream);
	APTKEnemyCharacter* Enemy = GetWorld()->SpawnActor<APTKEnemyCharacter>(
		EnemyClass, Where, FRotator::ZeroRotator, Params);
	if (!Enemy)
	{
		return false;
	}

	if (!RouteId.IsNone())
	{
		Enemy->AssignLaneRoute(RouteId);
	}

	if (UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld()))
	{
		Analytics->NotifyEnemySpawned(Enemy, RouteId);
	}

	// Scaling is applied to this instance only - never to the Blueprint. See the
	// header for why that distinction is load-bearing.
	const float HealthScale = GetHealthScaleForWave(CurrentWave);
	if (UPTKHealthComponent* Health = Enemy->GetHealthComponent())
	{
		Health->SetMaxHealth(Health->GetMaxHealth() * HealthScale);
		Health->ResetHealth();
	}
	Enemy->SetDamageMultiplier(GetDamageScaleForWave(CurrentWave));

	Live.Add(Enemy);
	return true;
}

void APTKWaveManager::PruneDead()
{
	Live.RemoveAll([](const TObjectPtr<APTKEnemyCharacter>& Enemy)
	{
		return !Enemy || !IsValid(Enemy) || Enemy->IsDead();
	});
}

int32 APTKWaveManager::GetEnemiesRemaining() const
{
	int32 Count = 0;
	for (const TObjectPtr<APTKEnemyCharacter>& Enemy : Live)
	{
		if (Enemy && IsValid(Enemy) && !Enemy->IsDead())
		{
			++Count;
		}
	}
	return Count + PendingRoster.Num();
}

TArray<APTKSpawnPortal*> APTKWaveManager::GetActivePortals() const
{
	TArray<APTKSpawnPortal*> Out;
	if (Phase == EPTKWavePhase::Warning || Phase == EPTKWavePhase::Spawning)
	{
		for (const TObjectPtr<APTKSpawnPortal>& Portal : ActivePortals)
		{
			if (Portal)
			{
				Out.Add(Portal);
			}
		}
	}
	return Out;
}

// Compounding rather than linear: wave 5 lands at 1.11^4 = 1.52x health, which
// is a real step up without the runaway a per-wave doubling would give.
float APTKWaveManager::GetHealthScaleForWave(int32 Wave) const
{
	return FMath::Pow(1.0f + HealthGrowthPerWave, FMath::Max(Wave - 1, 0));
}

float APTKWaveManager::GetDamageScaleForWave(int32 Wave) const
{
	return FMath::Pow(1.0f + DamageGrowthPerWave, FMath::Max(Wave - 1, 0));
}

void APTKWaveManager::DebugSkipToWave(int32 Wave)
{
	if (!Waves.IsValidIndex(Wave - 1))
	{
		UE_LOG(LogPTK, Warning, TEXT("WAVES | no wave %d"), Wave);
		return;
	}
	for (const TObjectPtr<APTKEnemyCharacter>& Enemy : Live)
	{
		if (Enemy && IsValid(Enemy))
		{
			Enemy->Destroy();
		}
	}
	Live.Reset();
	PendingRoster.Reset();
	BeginWave(Wave);
}

int32 APTKWaveManager::DebugSpawnExtra(int32 Count)
{
	if (Count <= 0 || EnemyTypes.Num() == 0)
	{
		return 0;
	}

	TArray<TSubclassOf<APTKEnemyCharacter>> Types;
	for (const TPair<FName, TSubclassOf<APTKEnemyCharacter>>& Pair : EnemyTypes)
	{
		if (Pair.Value)
		{
			Types.Add(Pair.Value);
		}
	}
	if (Types.Num() == 0)
	{
		return 0;
	}

	// Reuse the live wave's portals and lanes so the extra bodies behave
	// exactly like ordinary ones - same corners, same routes, same dealing.
	// If nothing is in flight, open every portal and every lane first.
	if (ActivePortals.Num() == 0)
	{
		for (TActorIterator<APTKSpawnPortal> It(GetWorld()); It; ++It)
		{
			ActivePortals.Add(*It);
		}
		ActiveRoutes.Reset();
		if (const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
		{
			for (const FPTKLaneRoute& Route : Field->GetRoutes())
			{
				ActiveRoutes.Add(Route.Id);
			}
		}
	}

	int32 Spawned = 0;
	for (int32 i = 0; i < Count; ++i)
	{
		if (SpawnOne(Types[Stream.RandRange(0, Types.Num() - 1)]))
		{
			++Spawned;
		}
	}

	UE_LOG(LogPTK, Warning, TEXT("WAVES | stress spawn | %d of %d requested | %d alive"),
		Spawned, Count, GetEnemiesRemaining());
	return Spawned;
}

FName APTKWaveManager::PickLaneFromPlan() const
{
	if (ActiveRoutes.Num() == 0)
	{
		return NAME_None;
	}

	const UPTKAdaptiveDirector* Director = UPTKAdaptiveDirector::Get(GetWorld());
	if (!Director)
	{
		return ActiveRoutes[Stream.RandRange(0, ActiveRoutes.Num() - 1)];
	}

	// Only lanes this wave actually opened are eligible - the plan covers every
	// lane on the map, but a wave still arrives through the corners it chose.
	const FPTKDirectorPlan Plan = Director->GetCurrentPlan();
	float Total = 0.0f;
	for (const FPTKLanePlan& Lane : Plan.Lanes)
	{
		if (ActiveRoutes.Contains(Lane.LaneId))
		{
			Total += FMath::Max(Lane.Pressure, 0.0f);
		}
	}
	if (Total <= KINDA_SMALL_NUMBER)
	{
		return ActiveRoutes[Stream.RandRange(0, ActiveRoutes.Num() - 1)];
	}

	float Roll = Stream.FRand() * Total;
	for (const FPTKLanePlan& Lane : Plan.Lanes)
	{
		if (!ActiveRoutes.Contains(Lane.LaneId))
		{
			continue;
		}
		Roll -= FMath::Max(Lane.Pressure, 0.0f);
		if (Roll <= 0.0f)
		{
			return Lane.LaneId;
		}
	}
	return ActiveRoutes.Last();
}

TSubclassOf<APTKEnemyCharacter> APTKWaveManager::PickEnemyForLane(FName LaneId) const
{
	if (!Waves.IsValidIndex(CurrentWave - 1))
	{
		return nullptr;
	}
	const FPTKWaveDefinition& Definition = Waves[CurrentWave - 1];

	// The director's bias for this lane, if it has one. Absent means x1.
	const TMap<FName, float>* Bias = nullptr;
	if (const UPTKAdaptiveDirector* Director = UPTKAdaptiveDirector::Get(GetWorld()))
	{
		const FPTKDirectorPlan Plan = Director->GetCurrentPlan();
		for (const FPTKLanePlan& Lane : Plan.Lanes)
		{
			if (Lane.LaneId == LaneId)
			{
				Bias = &Lane.TypeWeights;
				break;
			}
		}
	}

	// Reverse-map class back to id so the bias table, which is written in terms
	// of enemy ids, can be applied to the wave's composition entries.
	auto IdForClass = [this](const TSubclassOf<APTKEnemyCharacter>& Class) -> FName
	{
		for (const TPair<FName, TSubclassOf<APTKEnemyCharacter>>& Pair : EnemyTypes)
		{
			if (Pair.Value == Class)
			{
				return Pair.Key;
			}
		}
		return NAME_None;
	};

	float Total = 0.0f;
	TArray<float> Weights;
	Weights.Reserve(Definition.Composition.Num());
	for (const FPTKWaveEntry& Entry : Definition.Composition)
	{
		float Weight = (Entry.EnemyClass && Entry.Weight > 0)
			? static_cast<float>(Entry.Weight) : 0.0f;
		if (Weight > 0.0f && Bias)
		{
			if (const float* Multiplier = Bias->Find(IdForClass(Entry.EnemyClass)))
			{
				Weight *= FMath::Max(*Multiplier, 0.0f);
			}
		}
		Weights.Add(Weight);
		Total += Weight;
	}
	if (Total <= KINDA_SMALL_NUMBER)
	{
		return nullptr;
	}

	float Roll = Stream.FRand() * Total;
	for (int32 i = 0; i < Definition.Composition.Num(); ++i)
	{
		Roll -= Weights[i];
		if (Roll <= 0.0f)
		{
			return Definition.Composition[i].EnemyClass;
		}
	}
	return Definition.Composition.Last().EnemyClass;
}
