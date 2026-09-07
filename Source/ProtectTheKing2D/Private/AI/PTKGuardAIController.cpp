// Protect the King - 2D. The one guard AI.

#include "AI/PTKGuardAIController.h"
#include "Core/PTKGameModeBase.h"

#include "Characters/PTKEnemyCharacter.h"
#include "Characters/PTKGuardCharacter.h"
#include "Combat/PTKCombatTarget.h"
#include "Components/PTKHealthComponent.h"
#include "Core/PTKBattlefield.h"
#include "Core/PTKGuardBase.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKGuardAIController)

APTKGuardAIController::APTKGuardAIController()
{
	PrimaryActorTick.bCanEverTick = true;
	// A 2D guard has no line of sight to lose and no perception config to get
	// wrong; distance is the whole of its awareness.
	bAttachToPawn = false;
}

void APTKGuardAIController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);

	APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(InPawn);
	if (!Guard)
	{
		// Deliberately loud. This controller only knows how to drive a guard,
		// and silently possessing something else would look like broken AI.
		UE_LOG(LogPTK, Warning,
			TEXT("GUARD AI | %s possessed %s, which is not an APTKGuardCharacter"),
			*GetName(), *GetNameSafe(InPawn));
		return;
	}

	Target = nullptr;
	TargetRefreshTimer = 0.0f;
	DefendCooldownRemaining = 0.0f;
	AIState = EPTKGuardAIState::Hold;

	UE_LOG(LogPTK, Log,
		TEXT("GUARD AI | %s takes over %s | home (%.0f, %.0f) | detect %.0f | chase %.0f | reach %.0f"),
		*GetName(), *Guard->GetName(),
		Guard->GetHomePosition().X, Guard->GetHomePosition().Z,
		Guard->GetDetectionRange(), Guard->GetMaxChaseDistance(),
		Guard->GetAttackReach());
}

void APTKGuardAIController::OnUnPossess()
{
	// The player is taking this guard, or it is being destroyed. Either way the
	// AI must stop deciding things about a pawn it no longer holds.
	if (APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(GetPawn()))
	{
		Guard->SetMoveInput(FVector2D::ZeroVector);
		UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s releases %s"), *GetName(), *Guard->GetName());
	}
	Target = nullptr;
	AIState = EPTKGuardAIState::Inactive;
	Super::OnUnPossess();
}

void APTKGuardAIController::SetAIEnabled(bool bEnabled)
{
	if (bAIEnabled == bEnabled)
	{
		return;
	}
	bAIEnabled = bEnabled;
	if (!bEnabled)
	{
		if (APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(GetPawn()))
		{
			Guard->SetMoveInput(FVector2D::ZeroVector);
		}
		Target = nullptr;
		AIState = EPTKGuardAIState::Inactive;
	}
	else
	{
		AIState = EPTKGuardAIState::Hold;
	}
}

void APTKGuardAIController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (!APTKGameModeBase::IsGameplayActive(GetWorld())) return;

	APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(GetPawn());
	if (!Guard)
	{
		AIState = EPTKGuardAIState::Inactive;
		return;
	}

	if (Guard->IsDead())
	{
		// A corpse decides nothing. The death itself is handled entirely by
		// the character - this only stops the AI talking to it.
		if (AIState != EPTKGuardAIState::Dead)
		{
			UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s is dead - AI stopped"), *Guard->GetName());
			AIState = EPTKGuardAIState::Dead;
			Target = nullptr;
		}
		return;
	}

	if (!bAIEnabled)
	{
		return;
	}

	DefendCooldownRemaining = FMath::Max(0.0f, DefendCooldownRemaining - DeltaSeconds);
	TargetRefreshTimer -= DeltaSeconds;

	// Re-acquire when the current target is gone, has been dragged out of the
	// defended area, or the refresh interval has elapsed.
	if (!IsTargetStillValid(Guard, Target) || TargetRefreshTimer <= 0.0f)
	{
		TargetRefreshTimer = TargetRefreshInterval;
		AActor* const Found = FindTarget(Guard);
		if (Found != Target)
		{
			UE_LOG(LogPTK, Verbose, TEXT("GUARD AI | %s target: %s -> %s"),
				*Guard->GetName(), *GetNameSafe(Target), *GetNameSafe(Found));
			Target = Found;
		}
	}

	const FVector Here = Guard->GetActorLocation();

	if (bDrawAIRanges)
	{
		const FVector Home = Guard->GetHomePosition();
		DrawDebugCircle(GetWorld(), Home, Guard->GetMaxChaseDistance(), 32,
			FColor::Yellow, false, -1.0f, 0, 1.0f, FVector(1, 0, 0), FVector(0, 0, 1), false);
		DrawDebugCircle(GetWorld(), Here, Guard->GetAttackReach(), 24,
			FColor::Green, false, -1.0f, 0, 1.0f, FVector(1, 0, 0), FVector(0, 0, 1), false);
	}

	if (Target)
	{
		const FVector To = Target->GetActorLocation() - Here;
		const float Distance = To.Size();
		// Reach is the guard's OWN number, so this single line is what makes a
		// melee guard close and a ranged one hold its ground.
		const float EngageAt = Guard->GetAttackReach() * Guard->GetAIEngageFraction();

		ConsiderDefending(Guard, DeltaSeconds);

		if (Distance <= EngageAt)
		{
			AIState = EPTKGuardAIState::Attack;
			// Stop, face the target, swing. Facing has to be set explicitly:
			// the character only turns from movement input, and this guard is
			// deliberately standing still.
			Guard->SetMoveInput(FVector2D::ZeroVector);
			FaceLocation(Guard, Target->GetActorLocation());
			Guard->StartAttack();
		}
		else
		{
			AIState = EPTKGuardAIState::Engage;
			Guard->SetMoveInput(ToScreenInput(Guard, To));
		}
	}
	else
	{
		// Nothing local to fight. Priority is: help a neighbour who does have a
		// problem, otherwise go home. Defending its own ground is already
		// handled above by having found a Target at all, so reaching here means
		// this guard's own area is quiet.
		AssistRefreshTimer -= DeltaSeconds;

		// Drop an assist the moment it stops being one: the fight is over, the
		// ally died, or its base fell. Re-checked continuously rather than only
		// on the scan tick, so a guard never lingers at a finished fight.
		if (AssistTarget && (!IsValid(AssistTarget) || !IsThreatened(AssistTarget)))
		{
			UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s finished assisting %s"),
				*Guard->GetName(), *GetNameSafe(AssistTarget));
			AssistTarget = nullptr;
		}

		if (!AssistTarget && AssistRefreshTimer <= 0.0f)
		{
			AssistRefreshTimer = AssistRefreshInterval;
			if (AActor* Help = FindAssistTarget(Guard))
			{
				AssistTarget = Help;
				UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s assisting %s (%d already helping)"),
					*Guard->GetName(), *GetNameSafe(Help), CountAssistersOn(Help));
			}
		}

		if (AssistTarget)
		{
			const FVector ToHelp = AssistTarget->GetActorLocation() - Here;
			AIState = EPTKGuardAIState::Assist;
			// Stop short of the ally itself so helpers form a line beside it
			// rather than piling onto its exact position.
			if (ToHelp.Size() > AssistFightRadius * 0.5f)
			{
				Guard->SetMoveInput(ToScreenInput(Guard, ToHelp));
			}
			else
			{
				Guard->SetMoveInput(FVector2D::ZeroVector);
				FaceLocation(Guard, AssistTarget->GetActorLocation());
			}
		}
		else
		{
			// Back to the post it actually holds - never to wherever the last
			// fight happened to end.
			const FVector ToHome = Guard->GetHomePosition() - Here;
			if (ToHome.Size() <= Guard->GetAIHomeTolerance())
			{
				AIState = EPTKGuardAIState::Hold;
				Guard->SetMoveInput(FVector2D::ZeroVector);
			}
			else
			{
				AIState = EPTKGuardAIState::Return;
				Guard->SetMoveInput(ToScreenInput(Guard, ToHome));
			}
		}
	}

	if (AIState != LoggedState)
	{
		LoggedState = AIState;
		UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s -> %s | target %s"),
			*Guard->GetName(), *UPTKTypesLibrary::GuardAIStateToString(AIState),
			*GetNameSafe(Target));
	}
}

// ---------------------------------------------------------------------------
bool APTKGuardAIController::IsTargetStillValid(const APTKGuardCharacter* Guard,
	const AActor* Candidate) const
{
	if (!Guard || !PTKCombat::IsHostileTarget(Guard, Candidate))
	{
		return false;
	}
	// Bounded by distance from the ANCHOR, not from the guard. That is what
	// stops an enemy walking a guard off its ground one step at a time. While
	// assisting, the anchor is the fight it travelled to - see GetDefendAnchor.
	return FVector::Dist(GetDefendAnchor(Guard), Candidate->GetActorLocation())
		<= Guard->GetMaxChaseDistance();
}

FVector APTKGuardAIController::GetDefendAnchor(const APTKGuardCharacter* Guard) const
{
	if (AssistTarget && IsValid(AssistTarget))
	{
		return AssistTarget->GetActorLocation();
	}
	return Guard ? Guard->GetHomePosition() : FVector::ZeroVector;
}

bool APTKGuardAIController::IsThreatened(const AActor* Candidate) const
{
	if (!Candidate || !GetWorld())
	{
		return false;
	}

	// A destroyed base is not worth defending, and a dead guard cannot be helped.
	if (const APTKGuardBase* Base = Cast<APTKGuardBase>(Candidate))
	{
		if (Base->IsDestroyed())
		{
			return false;
		}
	}
	else if (const APTKGuardCharacter* Ally = Cast<APTKGuardCharacter>(Candidate))
	{
		if (Ally->IsDead())
		{
			return false;
		}
	}

	int32 Hostiles = 0;
	const FVector Where = Candidate->GetActorLocation();
	for (TActorIterator<APTKEnemyCharacter> It(GetWorld()); It; ++It)
	{
		APTKEnemyCharacter* const Enemy = *It;
		if (!IsValid(Enemy) || Enemy->IsDead())
		{
			continue;
		}
		if (FVector::DistSquared(Where, Enemy->GetActorLocation())
			<= FMath::Square(AssistFightRadius))
		{
			if (++Hostiles >= AssistThreatThreshold)
			{
				return true;
			}
		}
	}
	return false;
}

int32 APTKGuardAIController::CountAssistersOn(const AActor* Threat) const
{
	if (!Threat || !GetWorld())
	{
		return 0;
	}
	// Counted by asking the other controllers directly. With four AI guards this
	// is cheaper than maintaining a shared reservation table, and it cannot go
	// stale when a guard dies, is possessed by the player, or gives up.
	int32 Count = 0;
	for (TActorIterator<APTKGuardAIController> It(GetWorld()); It; ++It)
	{
		const APTKGuardAIController* Other = *It;
		if (Other && Other != this && Other->GetAssistTarget() == Threat
			&& Other->GetPawn() != nullptr)
		{
			++Count;
		}
	}
	return Count;
}

AActor* APTKGuardAIController::FindAssistTarget(const APTKGuardCharacter* Guard) const
{
	if (!Guard || !GetWorld())
	{
		return nullptr;
	}

	// A badly hurt guard holds its own ground rather than running to someone
	// else's fight, where it would simply die further from home.
	if (const UPTKHealthComponent* Health = Guard->GetHealthComponent())
	{
		if (Health->GetHealthFraction() < AssistMinHealthFraction)
		{
			return nullptr;
		}
	}

	const FVector Home = Guard->GetHomePosition();
	AActor* Best = nullptr;
	float BestSq = FMath::Square(AssistRadius);

	auto Consider = [this, Guard, &Home, &Best, &BestSq](AActor* Candidate)
	{
		if (!Candidate || Candidate == Guard)
		{
			return;
		}
		const float Sq = FVector::DistSquared(Home, Candidate->GetActorLocation());
		if (Sq >= BestSq)
		{
			return;
		}
		if (!IsThreatened(Candidate))
		{
			return;
		}
		// Refuse a fight that already has enough help. This is the whole of
		// "do not dogpile" - checked before claiming, so two guards deciding on
		// the same frame cannot both slip past a limit of one.
		if (CountAssistersOn(Candidate) >= MaxAssistGuardsPerThreat)
		{
			return;
		}
		BestSq = Sq;
		Best = Candidate;
	};

	if (const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		for (const TObjectPtr<APTKGuardCharacter>& Ally : Field->GetGuards())
		{
			Consider(Ally);
		}
		for (const TObjectPtr<APTKGuardBase>& Base : Field->GetBases())
		{
			Consider(Base);
		}
	}
	return Best;
}

AActor* APTKGuardAIController::FindTarget(const APTKGuardCharacter* Guard) const
{
	if (!Guard || !GetWorld())
	{
		return nullptr;
	}

	const FVector Here = Guard->GetActorLocation();
	const FVector Anchor = GetDefendAnchor(Guard);
	const float Detection = Guard->GetDetectionRange();
	const float Leash = Guard->GetMaxChaseDistance();

	AActor* Best = nullptr;
	float BestDistanceSq = TNumericLimits<float>::Max();

	// Hostility comes from the shared rule, so a guard can never pick another
	// guard or the King: they are different teams but the same side.
	for (TActorIterator<APTKTopDownCharacter> It(GetWorld()); It; ++It)
	{
		AActor* const Candidate = *It;
		if (!PTKCombat::IsHostileTarget(Guard, Candidate))
		{
			continue;
		}
		const FVector Where = Candidate->GetActorLocation();
		if (FVector::Dist(Anchor, Where) > Leash)
		{
			continue;
		}
		const float DistanceSq = FVector::DistSquared(Here, Where);
		if (DistanceSq > Detection * Detection)
		{
			continue;
		}
		if (DistanceSq < BestDistanceSq)
		{
			BestDistanceSq = DistanceSq;
			Best = Candidate;
		}
	}
	return Best;
}

int32 APTKGuardAIController::CountHostilesWithin(const APTKGuardCharacter* Guard,
	float Radius) const
{
	if (!Guard || !GetWorld())
	{
		return 0;
	}
	const FVector Here = Guard->GetActorLocation();
	int32 Count = 0;
	for (TActorIterator<APTKTopDownCharacter> It(GetWorld()); It; ++It)
	{
		if (PTKCombat::IsHostileTarget(Guard, *It)
			&& FVector::Dist(Here, It->GetActorLocation()) <= Radius)
		{
			++Count;
		}
	}
	return Count;
}

FVector2D APTKGuardAIController::ToScreenInput(const APTKGuardCharacter* Guard,
	const FVector& WorldOffset) const
{
	if (!Guard)
	{
		return FVector2D::ZeroVector;
	}
	// Projected onto the camera's basis rather than onto world axes - screen
	// right is not +X in this project, and the AI must not be the one place
	// that forgets it.
	const FVector2D Screen(
		FVector::DotProduct(WorldOffset, Guard->GetMovementRightVector()),
		FVector::DotProduct(WorldOffset, Guard->GetMovementUpVector()));
	return Screen.GetSafeNormal();
}

void APTKGuardAIController::FaceLocation(APTKGuardCharacter* Guard, const FVector& Where) const
{
	if (!Guard)
	{
		return;
	}
	const FVector2D Bearing = ToScreenInput(Guard, Where - Guard->GetActorLocation());
	if (Bearing.IsNearlyZero())
	{
		return;
	}
	Guard->SetFacingDirection(UPTKTypesLibrary::DirectionFromInput(
		Bearing, Guard->GetFacingDirection(), 0.0f, 0.0f));
}

void APTKGuardAIController::ConsiderDefending(APTKGuardCharacter* Guard, float /*DeltaSeconds*/)
{
	if (DefendCooldownRemaining > 0.0f || Guard->IsDefending() || Guard->IsAttacking())
	{
		return;
	}
	if (CountHostilesWithin(Guard, Guard->GetAttackReach()) < Guard->GetAIDefendMinEnemies())
	{
		return;
	}
	// No check for "is this Aegis" anywhere: StartDefend refuses without
	// defence art, so every other guard silently declines.
	if (Guard->StartDefend())
	{
		DefendCooldownRemaining = Guard->GetAIDefendCooldown();
		UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s raises its shield (next in %.0fs)"),
			*Guard->GetName(), DefendCooldownRemaining);
	}
}
