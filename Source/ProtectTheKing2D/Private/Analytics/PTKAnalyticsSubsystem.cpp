// Protect the King - 2D. Watches a run and writes down what happened.

#include "Analytics/PTKAnalyticsSubsystem.h"

#include "AI/PTKGuardAIController.h"
#include "Algo/Accumulate.h"
#include "Characters/PTKEnemyCharacter.h"
#include "Characters/PTKGuardCharacter.h"
#include "Characters/PTKKingCharacter.h"
#include "Components/PTKHealthComponent.h"
#include "Core/PTKBattlefield.h"
#include "Core/PTKGuardBase.h"
#include "Engine/World.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKAnalyticsSubsystem)

namespace
{
	/** Share of Part in Total, safe when Total is zero. */
	float Share(float Part, float Total)
	{
		return Total > KINDA_SMALL_NUMBER ? FMath::Clamp(Part / Total, 0.0f, 1.0f) : 0.0f;
	}
}

UPTKAnalyticsSubsystem* UPTKAnalyticsSubsystem::Get(const UWorld* World)
{
	return World ? World->GetSubsystem<UPTKAnalyticsSubsystem>() : nullptr;
}

TStatId UPTKAnalyticsSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UPTKAnalyticsSubsystem, STATGROUP_Tickables);
}

bool UPTKAnalyticsSubsystem::DoesSupportWorldType(const EWorldType::Type Type) const
{
	// Game and PIE only. An editor world has no run to observe.
	return Type == EWorldType::Game || Type == EWorldType::PIE;
}

// ---------------------------------------------------------------------------
// Binding
// ---------------------------------------------------------------------------

void UPTKAnalyticsSubsystem::EnsureBound()
{
	if (bBound)
	{
		return;
	}
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	if (!Field)
	{
		return;
	}

	// AddUniqueDynamic throughout: binding is attempted until it succeeds, and
	// a second successful pass must not double-count every point of damage.
	for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
	{
		if (UPTKHealthComponent* Health = Guard ? Guard->GetHealthComponent() : nullptr)
		{
			Health->OnHealthChanged.AddUniqueDynamic(this, &UPTKAnalyticsSubsystem::HandleGuardHealth);
			Health->OnDeath.AddUniqueDynamic(this, &UPTKAnalyticsSubsystem::HandleGuardDeath);
		}
	}

	for (const TObjectPtr<APTKGuardBase>& Base : Field->GetBases())
	{
		if (UPTKHealthComponent* Health = Base ? Base->GetHealthComponent() : nullptr)
		{
			Health->OnHealthChanged.AddUniqueDynamic(this, &UPTKAnalyticsSubsystem::HandleBaseHealth);
			BaseByHealth.Add(Health, Base->GetGuardId());
		}
	}

	if (APTKKingCharacter* King = Field->GetKing())
	{
		if (UPTKHealthComponent* Health = King->GetHealthComponent())
		{
			Health->OnHealthChanged.AddUniqueDynamic(this, &UPTKAnalyticsSubsystem::HandleKingHealth);
		}
	}

	// A guard defends the base of the same name, and each lane names the base
	// it runs through - so the guard's lane is whichever route ends at its own
	// base. Built once, because none of it moves during a run.
	for (const FPTKLaneRoute& Route : Field->GetRoutes())
	{
		if (!LaneOfGuard.Contains(Route.BaseId))
		{
			LaneOfGuard.Add(Route.BaseId, Route.Id);
		}
	}

	bBound = true;
	UE_LOG(LogPTK, Log, TEXT("ANALYTICS | bound to %d guards, %d bases and the King"),
		Field->GetGuards().Num(), Field->GetBases().Num());
}

// ---------------------------------------------------------------------------
// Wave boundaries
// ---------------------------------------------------------------------------

void UPTKAnalyticsSubsystem::NotifyWaveBegan(int32 WaveNumber)
{
	EnsureBound();

	Live = FPTKWaveSnapshot();
	Live.WaveNumber = WaveNumber;
	SwitchIntervals.Reset();
	LiveEnemies.Reset();
	EnemyLane.Reset();

	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
	WaveStartTime = Now;
	LastSwitchTime = Now;
	// The guard already in hand keeps accumulating from the wave boundary
	// rather than from when it was taken over, which was in the last wave.
	PossessionStartTime = Now;
	SampleTimer = 0.0f;

	// Seed a row per guard and per lane so a guard that did nothing and a lane
	// nothing came down still appear in the snapshot as zeroes. A missing row
	// and a row of zeroes mean different things.
	if (const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
		{
			if (Guard)
			{
				FPTKGuardWaveStats& Row = GuardRow(Guard->GetGuardId());
				Row.bAlive = !Guard->IsDead();
			}
		}
		for (const FPTKLaneRoute& Route : Field->GetRoutes())
		{
			FPTKLaneWaveStats& Row = LaneRow(Route.Id);
			Row.BaseId = Route.BaseId;
			if (const APTKGuardBase* Base = Field->FindBaseForGuard(Route.BaseId))
			{
				Row.bBaseDestroyed = Base->IsDestroyed();
			}
		}
	}

	bTracking = true;
	UE_LOG(LogPTK, Log, TEXT("ANALYTICS | wave %d tracking started"), WaveNumber);
}

void UPTKAnalyticsSubsystem::NotifyWaveEnded(int32 WaveNumber)
{
	if (!bTracking)
	{
		return;
	}

	// Bank the time the current guard has been held. Without this, the guard
	// the player is holding when the wave ends loses that whole stretch.
	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
	if (PossessedGuard)
	{
		GuardRow(PossessedGuard->GetGuardId()).PlayerControlledSeconds +=
			FMath::Max(0.0f, Now - PossessionStartTime);
		PossessionStartTime = Now;
	}

	Live.DurationSeconds = FMath::Max(0.0f, Now - WaveStartTime);
	ScoreSnapshot(Live);
	Snapshots.Add(Live);
	bTracking = false;

	UE_LOG(LogPTK, Log,
		TEXT("ANALYTICS | wave %d frozen | %.0fs | %d switches (%s) | %d guards, %d lanes, %d enemy types"),
		WaveNumber, Live.DurationSeconds, Live.Switching.TotalSwitches,
		Live.Switching.Tempo == EPTKSwitchTempo::High ? TEXT("HIGH")
			: Live.Switching.Tempo == EPTKSwitchTempo::Medium ? TEXT("MEDIUM") : TEXT("LOW"),
		Live.Guards.Num(), Live.Lanes.Num(), Live.EnemyTypes.Num());
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

void UPTKAnalyticsSubsystem::NotifyEnemySpawned(APTKEnemyCharacter* Enemy, FName LaneId)
{
	if (!Enemy)
	{
		return;
	}
	EnsureBound();

	LiveEnemies.Add(Enemy);
	EnemyLane.Add(Enemy, LaneId);

	if (UPTKHealthComponent* Health = Enemy->GetHealthComponent())
	{
		Health->OnHealthChanged.AddUniqueDynamic(this, &UPTKAnalyticsSubsystem::HandleEnemyHealth);
		Health->OnDeath.AddUniqueDynamic(this, &UPTKAnalyticsSubsystem::HandleEnemyDeath);
	}

	if (!bTracking)
	{
		return;
	}
	++EnemyRow(Enemy->GetEnemyId()).Spawned;
	if (!LaneId.IsNone())
	{
		++LaneRow(LaneId).EnemiesSpawned;
	}
}

void UPTKAnalyticsSubsystem::NotifyPossession(APTKGuardCharacter* Guard)
{
	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;

	// Bank whatever the outgoing guard was owed before switching the clock.
	if (bTracking && PossessedGuard)
	{
		GuardRow(PossessedGuard->GetGuardId()).PlayerControlledSeconds +=
			FMath::Max(0.0f, Now - PossessionStartTime);
	}

	const bool bIsSwitch = bTracking && PossessedGuard != nullptr
		&& Guard != nullptr && Guard != PossessedGuard;

	PossessedGuard = Guard;
	PossessionStartTime = Now;

	if (bIsSwitch)
	{
		++Live.Switching.TotalSwitches;
		SwitchIntervals.Add(FMath::Max(0.0f, Now - LastSwitchTime));
		LastSwitchTime = Now;
		++GuardRow(Guard->GetGuardId()).TimesSwitchedInto;
	}
}

void UPTKAnalyticsSubsystem::NotifyKingPower(APTKGuardCharacter* Guard)
{
	if (bTracking && Guard)
	{
		GuardRow(Guard->GetGuardId()).bReceivedKingPower = true;
	}
}

void UPTKAnalyticsSubsystem::NotifyBaseDestroyed(APTKGuardBase* Base)
{
	if (!bTracking || !Base)
	{
		return;
	}
	if (const FName* LaneId = LaneOfGuard.Find(Base->GetGuardId()))
	{
		LaneRow(*LaneId).bBaseDestroyed = true;
	}
}

// ---------------------------------------------------------------------------
// Damage and death
// ---------------------------------------------------------------------------

void UPTKAnalyticsSubsystem::HandleGuardHealth(UPTKHealthComponent* Component,
	float /*NewHealth*/, float Delta, AActor* Instigator)
{
	// Delta is negative for damage. Healing is not damage taken.
	if (!bTracking || Delta >= 0.0f || !Component)
	{
		return;
	}
	const float Damage = -Delta;

	const APTKGuardCharacter* Guard = Cast<APTKGuardCharacter>(Component->GetOwner());
	if (!Guard)
	{
		return;
	}
	GuardRow(Guard->GetGuardId()).DamageTaken += Damage;

	// Attribute to the lane the guard defends, and to the enemy type that did
	// it. Both are read from the instigator rather than assumed.
	if (const FName* LaneId = LaneOfGuard.Find(Guard->GetGuardId()))
	{
		LaneRow(*LaneId).GuardDamageTaken += Damage;
	}
	if (const APTKEnemyCharacter* Enemy = Cast<APTKEnemyCharacter>(Instigator))
	{
		EnemyRow(Enemy->GetEnemyId()).DamageToGuards += Damage;
	}
}

void UPTKAnalyticsSubsystem::HandleGuardDeath(UPTKHealthComponent* Component, AActor* Killer)
{
	if (!bTracking || !Component)
	{
		return;
	}
	if (const APTKGuardCharacter* Guard = Cast<APTKGuardCharacter>(Component->GetOwner()))
	{
		GuardRow(Guard->GetGuardId()).bAlive = false;
	}
	if (const APTKEnemyCharacter* Enemy = Cast<APTKEnemyCharacter>(Killer))
	{
		++EnemyRow(Enemy->GetEnemyId()).GuardKills;
	}
}

void UPTKAnalyticsSubsystem::HandleEnemyHealth(UPTKHealthComponent* Component,
	float /*NewHealth*/, float Delta, AActor* Instigator)
{
	if (!bTracking || Delta >= 0.0f || !Component)
	{
		return;
	}
	// Damage DEALT by a guard is the same event as damage taken by an enemy,
	// seen from the other side - so it is counted here rather than needing the
	// attacker to report its own swings.
	if (const APTKGuardCharacter* Guard = Cast<APTKGuardCharacter>(Instigator))
	{
		GuardRow(Guard->GetGuardId()).DamageDealt += -Delta;
	}
}

void UPTKAnalyticsSubsystem::HandleEnemyDeath(UPTKHealthComponent* Component, AActor* Killer)
{
	if (!Component)
	{
		return;
	}
	AActor* const Owner = Component->GetOwner();
	LiveEnemies.RemoveAllSwap([Owner](const TObjectPtr<APTKEnemyCharacter>& E)
		{ return E == Owner || !IsValid(E); }, EAllowShrinking::No);

	if (!bTracking)
	{
		return;
	}
	if (const APTKEnemyCharacter* Enemy = Cast<APTKEnemyCharacter>(Owner))
	{
		++EnemyRow(Enemy->GetEnemyId()).Died;
		const FName LaneId = LaneOf(Enemy);
		if (!LaneId.IsNone())
		{
			++LaneRow(LaneId).EnemyKills;
		}
	}
	if (const APTKGuardCharacter* Guard = Cast<APTKGuardCharacter>(Killer))
	{
		++GuardRow(Guard->GetGuardId()).Kills;
	}
}

void UPTKAnalyticsSubsystem::HandleBaseHealth(UPTKHealthComponent* Component,
	float /*NewHealth*/, float Delta, AActor* Instigator)
{
	if (!bTracking || Delta >= 0.0f || !Component)
	{
		return;
	}
	const float Damage = -Delta;
	if (const FName* BaseId = BaseByHealth.Find(Component))
	{
		if (const FName* LaneId = LaneOfGuard.Find(*BaseId))
		{
			LaneRow(*LaneId).BaseDamageTaken += Damage;
		}
	}
	if (const APTKEnemyCharacter* Enemy = Cast<APTKEnemyCharacter>(Instigator))
	{
		EnemyRow(Enemy->GetEnemyId()).DamageToBases += Damage;
	}
}

void UPTKAnalyticsSubsystem::HandleKingHealth(UPTKHealthComponent* /*Component*/,
	float /*NewHealth*/, float Delta, AActor* Instigator)
{
	if (!bTracking || Delta >= 0.0f)
	{
		return;
	}
	const float Damage = -Delta;
	if (const APTKEnemyCharacter* Enemy = Cast<APTKEnemyCharacter>(Instigator))
	{
		EnemyRow(Enemy->GetEnemyId()).DamageToKing += Damage;
		// Charged to the lane that enemy walked in on, which is the only
		// meaningful sense in which the core took damage "from" a direction.
		const FName LaneId = LaneOf(Enemy);
		if (!LaneId.IsNone())
		{
			LaneRow(LaneId).KingDamageFromLane += Damage;
		}
	}
}

// ---------------------------------------------------------------------------
// Sampling
// ---------------------------------------------------------------------------

void UPTKAnalyticsSubsystem::Tick(float DeltaTime)
{
	if (!bTracking)
	{
		return;
	}
	SampleTimer += DeltaTime;
	if (SampleTimer < SampleInterval)
	{
		return;
	}
	SamplePresenceAndProgress(SampleTimer);
	SampleTimer = 0.0f;
}

void UPTKAnalyticsSubsystem::SamplePresenceAndProgress(float Elapsed)
{
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	if (!Field)
	{
		return;
	}

	// PRESENCE. The player-driven guard and the assisting AI guards are
	// credited to SEPARATE counters - a lane the AI covered is not a lane the
	// player defended, and summing them would erase the distinction the whole
	// metric exists to draw.
	for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
	{
		if (!Guard || Guard->IsDead())
		{
			continue;
		}
		const bool bPlayer = (Guard == PossessedGuard);
		bool bAssisting = false;
		if (!bPlayer)
		{
			const APTKGuardAIController* AI = Cast<APTKGuardAIController>(Guard->GetController());
			bAssisting = AI && AI->GetAIState() == EPTKGuardAIState::Assist;
		}
		if (!bPlayer && !bAssisting)
		{
			continue;
		}

		// Nearest lane, if close enough to count as being on one.
		FName Nearest = NAME_None;
		float Best = LanePresenceRadius;
		for (const FPTKLaneRoute& Route : Field->GetRoutes())
		{
			const float Distance = Field->DistanceToRoute(Route.Id, Guard->GetActorLocation());
			if (Distance < Best)
			{
				Best = Distance;
				Nearest = Route.Id;
			}
		}
		if (Nearest.IsNone())
		{
			continue;
		}
		FPTKLaneWaveStats& Row = LaneRow(Nearest);
		(bPlayer ? Row.PlayerPresenceSeconds : Row.AIAssistPresenceSeconds) += Elapsed;
	}

	// PROGRESS, over the cached list rather than an actor scan.
	for (int32 i = LiveEnemies.Num() - 1; i >= 0; --i)
	{
		APTKEnemyCharacter* const Enemy = LiveEnemies[i];
		if (!IsValid(Enemy) || Enemy->IsDead())
		{
			LiveEnemies.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		const float Progress = Enemy->GetLaneProgress();
		FPTKEnemyTypeWaveStats& Type = EnemyRow(Enemy->GetEnemyId());
		Type.DeepestProgress = FMath::Max(Type.DeepestProgress, Progress);

		const FName LaneId = LaneOf(Enemy);
		if (!LaneId.IsNone())
		{
			FPTKLaneWaveStats& Row = LaneRow(LaneId);
			Row.DeepestProgress = FMath::Max(Row.DeepestProgress, Progress);
			if (Progress >= BreachProgress)
			{
				Row.bBreached = true;
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

FPTKGuardWaveStats& UPTKAnalyticsSubsystem::GuardRow(FName GuardId)
{
	for (FPTKGuardWaveStats& Row : Live.Guards)
	{
		if (Row.GuardId == GuardId)
		{
			return Row;
		}
	}
	FPTKGuardWaveStats Row;
	Row.GuardId = GuardId;
	return Live.Guards[Live.Guards.Add(MoveTemp(Row))];
}

FPTKLaneWaveStats& UPTKAnalyticsSubsystem::LaneRow(FName LaneId)
{
	for (FPTKLaneWaveStats& Row : Live.Lanes)
	{
		if (Row.LaneId == LaneId)
		{
			return Row;
		}
	}
	FPTKLaneWaveStats Row;
	Row.LaneId = LaneId;
	return Live.Lanes[Live.Lanes.Add(MoveTemp(Row))];
}

FPTKEnemyTypeWaveStats& UPTKAnalyticsSubsystem::EnemyRow(FName EnemyId)
{
	for (FPTKEnemyTypeWaveStats& Row : Live.EnemyTypes)
	{
		if (Row.EnemyId == EnemyId)
		{
			return Row;
		}
	}
	FPTKEnemyTypeWaveStats Row;
	Row.EnemyId = EnemyId;
	return Live.EnemyTypes[Live.EnemyTypes.Add(MoveTemp(Row))];
}

FName UPTKAnalyticsSubsystem::LaneOf(const AActor* Enemy) const
{
	const FName* Found = EnemyLane.Find(Enemy);
	return Found ? *Found : NAME_None;
}

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

void UPTKAnalyticsSubsystem::ScoreSnapshot(FPTKWaveSnapshot& Snapshot) const
{
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());

	// --- switching -----------------------------------------------------
	float TotalControl = 0.0f;
	for (const FPTKGuardWaveStats& Row : Snapshot.Guards)
	{
		TotalControl += Row.PlayerControlledSeconds;
	}
	Snapshot.TotalPlayerControlledSeconds = TotalControl;

	FPTKSwitchStats& Switching = Snapshot.Switching;
	const float Minutes = Snapshot.DurationSeconds / 60.0f;
	Switching.SwitchesPerMinute = Minutes > KINDA_SMALL_NUMBER
		? Switching.TotalSwitches / Minutes : 0.0f;
	Switching.AverageSecondsBetween = SwitchIntervals.Num() > 0
		? Algo::Accumulate(SwitchIntervals, 0.0f) / SwitchIntervals.Num()
		: Snapshot.DurationSeconds;
	Switching.Tempo =
		Switching.SwitchesPerMinute >= HighSwitchesPerMinute ? EPTKSwitchTempo::High
		: Switching.SwitchesPerMinute > LowSwitchesPerMinute ? EPTKSwitchTempo::Medium
		: EPTKSwitchTempo::Low;

	for (FPTKGuardWaveStats& Row : Snapshot.Guards)
	{
		Row.PlayerControlFraction = Share(Row.PlayerControlledSeconds, TotalControl);
		if (Row.PlayerControlFraction >= SingleGuardFocusFraction)
		{
			Switching.bSingleGuardFocus = true;
			Switching.FocusGuardId = Row.GuardId;
		}
		if (Field)
		{
			for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
			{
				if (Guard && Guard->GetGuardId() == Row.GuardId)
				{
					Row.bAlive = !Guard->IsDead();
					Row.HealthFraction = Guard->GetHealthComponent()
						? Guard->GetHealthComponent()->GetHealthFraction() : 0.0f;
				}
			}
		}
	}

	// --- lane vulnerability --------------------------------------------
	//
	// Every factor is clamped to 0..1 and then weighted, so the worst any one
	// of them can contribute is its own weight. That is what keeps a single
	// dramatic event - a destroyed base, say - from pinning the whole score at
	// 1.0 and hiding everything else about the lane.
	float TotalPresence = 0.0f;
	for (const FPTKLaneWaveStats& Row : Snapshot.Lanes)
	{
		TotalPresence += Row.PlayerPresenceSeconds;
	}

	for (FPTKLaneWaveStats& Row : Snapshot.Lanes)
	{
		const APTKGuardBase* Base = Field ? Field->FindBaseForGuard(Row.BaseId) : nullptr;
		const float BaseMax = (Base && Base->GetHealthComponent())
			? Base->GetHealthComponent()->GetMaxHealth() : 2500.0f;

		const float BaseDamage = Share(Row.BaseDamageTaken, BaseMax);
		const float GuardDamage = Share(Row.GuardDamageTaken, GuardDamageReference);
		const float Progress = FMath::Clamp(Row.DeepestProgress, 0.0f, 1.0f);
		const float LowPresence = 1.0f - Share(Row.PlayerPresenceSeconds, TotalPresence);
		const float Breach = Row.bBreached ? 1.0f : 0.0f;
		const float Destroyed = Row.bBaseDestroyed ? 1.0f : 0.0f;

		// A lane where NOTHING happened is not vulnerable, it is untouched.
		// Without this, every quiet lane would score on "low player presence"
		// alone and the metric would point at the calmest parts of the map.
		//
		// "Nothing happened" deliberately means no damage and no advance, not
		// merely no spawns. A lane can be hurt by enemies that arrived along a
		// different route, and an earlier version keyed only on the spawn count
		// scored a base that had lost most of its health at 0.0 because nothing
		// had been dealt onto that particular lane.
		const bool bUntouched = Row.EnemiesSpawned == 0
			&& Row.BaseDamageTaken <= 0.0f
			&& Row.GuardDamageTaken <= 0.0f
			&& Row.DeepestProgress <= 0.0f
			&& !Row.bBaseDestroyed;
		if (bUntouched)
		{
			Row.Vulnerability = 0.0f;
			continue;
		}

		Row.Vulnerability = FMath::Clamp(
			BaseDamage * WeightBaseDamage
			+ GuardDamage * WeightGuardDamage
			+ Progress * WeightEnemyProgress
			+ LowPresence * WeightLowPlayerPresence
			+ Breach * WeightBreach
			+ Destroyed * WeightBaseDestroyed,
			0.0f, 1.0f);
	}

	// --- guard dominance -----------------------------------------------
	int32 TotalKills = 0;
	float TotalDealt = 0.0f;
	for (const FPTKGuardWaveStats& Row : Snapshot.Guards)
	{
		TotalKills += Row.Kills;
		TotalDealt += Row.DamageDealt;
	}

	for (FPTKGuardWaveStats& Row : Snapshot.Guards)
	{
		// The lane this guard is responsible for; its success is part of the
		// guard's score, so a guard that held a quiet line still reads as
		// having done its job.
		float LaneSuccess = 1.0f;
		if (const FName* LaneId = LaneOfGuard.Find(Row.GuardId))
		{
			for (const FPTKLaneWaveStats& Lane : Snapshot.Lanes)
			{
				if (Lane.LaneId == *LaneId)
				{
					LaneSuccess = 1.0f - Lane.Vulnerability;
				}
			}
		}

		const float Survival = Row.bAlive ? FMath::Clamp(Row.HealthFraction, 0.0f, 1.0f) : 0.0f;

		Row.Dominance = FMath::Clamp(
			Share(static_cast<float>(Row.Kills), static_cast<float>(TotalKills)) * WeightKillShare
			+ Share(Row.DamageDealt, TotalDealt) * WeightDamageShare
			+ Survival * WeightSurvival
			+ Row.PlayerControlFraction * WeightPlayerUsage
			+ LaneSuccess * WeightLaneSuccess,
			0.0f, 1.0f);
	}

	// --- enemy effectiveness -------------------------------------------
	float MaxGuardDamage = 0.0f;
	float MaxBaseDamage = 0.0f;
	float MaxKingDamage = 0.0f;
	for (const FPTKEnemyTypeWaveStats& Row : Snapshot.EnemyTypes)
	{
		MaxGuardDamage = FMath::Max(MaxGuardDamage, Row.DamageToGuards);
		MaxBaseDamage = FMath::Max(MaxBaseDamage, Row.DamageToBases);
		MaxKingDamage = FMath::Max(MaxKingDamage, Row.DamageToKing);
	}

	for (FPTKEnemyTypeWaveStats& Row : Snapshot.EnemyTypes)
	{
		Row.SurvivalFraction = Row.Spawned > 0
			? FMath::Clamp(1.0f - static_cast<float>(Row.Died) / Row.Spawned, 0.0f, 1.0f)
			: 0.0f;

		// Scored against the best performer of the wave rather than against an
		// absolute number, so the scale stays meaningful whatever the wave's
		// size or composition.
		Row.Effectiveness = FMath::Clamp(
			Share(Row.DamageToGuards, MaxGuardDamage) * WeightDamageToGuards
			+ Share(Row.DamageToBases, MaxBaseDamage) * WeightDamageToBases
			+ Share(Row.DamageToKing, MaxKingDamage) * WeightDamageToKing
			+ Row.SurvivalFraction * WeightEnemySurvival
			+ FMath::Clamp(Row.DeepestProgress, 0.0f, 1.0f) * WeightEnemyProgressReached,
			0.0f, 1.0f);
	}
}

// ---------------------------------------------------------------------------
// Reading
// ---------------------------------------------------------------------------

FPTKWaveSnapshot UPTKAnalyticsSubsystem::GetLastSnapshot() const
{
	return Snapshots.Num() > 0 ? Snapshots.Last() : FPTKWaveSnapshot();
}

FPTKWaveSnapshot UPTKAnalyticsSubsystem::GetLiveSnapshot() const
{
	FPTKWaveSnapshot Copy = Live;
	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
	Copy.DurationSeconds = FMath::Max(0.0f, Now - WaveStartTime);

	// Include the stretch the current guard is part-way through, so a live read
	// is not systematically short by however long ago the last switch was.
	if (PossessedGuard)
	{
		for (FPTKGuardWaveStats& Row : Copy.Guards)
		{
			if (Row.GuardId == PossessedGuard->GetGuardId())
			{
				Row.PlayerControlledSeconds += FMath::Max(0.0f, Now - PossessionStartTime);
			}
		}
	}
	ScoreSnapshot(Copy);
	return Copy;
}

void UPTKAnalyticsSubsystem::LogHistory() const
{
	UE_LOG(LogPTK, Warning, TEXT("ANALYTICS | %d wave(s) recorded"), Snapshots.Num());
	for (const FPTKWaveSnapshot& Wave : Snapshots)
	{
		UE_LOG(LogPTK, Warning, TEXT("  WAVE %d | %.0fs | %d switches, %.1f/min | focus %s"),
			Wave.WaveNumber, Wave.DurationSeconds, Wave.Switching.TotalSwitches,
			Wave.Switching.SwitchesPerMinute,
			Wave.Switching.bSingleGuardFocus ? *Wave.Switching.FocusGuardId.ToString() : TEXT("none"));
		for (const FPTKGuardWaveStats& G : Wave.Guards)
		{
			UE_LOG(LogPTK, Warning,
				TEXT("    %-9s ctrl %5.1fs (%3.0f%%) | dealt %6.0f | kills %2d | taken %6.0f | dom %.2f%s"),
				*G.GuardId.ToString(), G.PlayerControlledSeconds, G.PlayerControlFraction * 100.0f,
				G.DamageDealt, G.Kills, G.DamageTaken, G.Dominance,
				G.bReceivedKingPower ? TEXT(" [empowered]") : TEXT(""));
		}
		for (const FPTKLaneWaveStats& L : Wave.Lanes)
		{
			UE_LOG(LogPTK, Warning,
				TEXT("    lane %-12s spawned %2d killed %2d | deepest %.2f | player %4.1fs ai %4.1fs | base -%.0f | vuln %.2f%s"),
				*L.LaneId.ToString(), L.EnemiesSpawned, L.EnemyKills, L.DeepestProgress,
				L.PlayerPresenceSeconds, L.AIAssistPresenceSeconds, L.BaseDamageTaken,
				L.Vulnerability, L.bBaseDestroyed ? TEXT(" DESTROYED") : TEXT(""));
		}
		for (const FPTKEnemyTypeWaveStats& E : Wave.EnemyTypes)
		{
			UE_LOG(LogPTK, Warning,
				TEXT("    %-12s spawned %2d died %2d | guards -%.0f bases -%.0f king -%.0f | eff %.2f"),
				*E.EnemyId.ToString(), E.Spawned, E.Died, E.DamageToGuards,
				E.DamageToBases, E.DamageToKing, E.Effectiveness);
		}
	}
}
